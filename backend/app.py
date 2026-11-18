"""Serve the Skan Coach catalog from the local SQLite database."""

from __future__ import annotations

import json
import csv
from email.message import EmailMessage
import hmac
import os
import re
import smtplib
import ssl
import time
from threading import Lock, Thread
import subprocess
import sqlite3
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .database import DATABASE_ERRORS, connect_database, initialize_postgres_catalog, seed_postgres_community_data
from .import_youtube_playlist import MANUAL_OVERRIDES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "skan_coach.db"
HOST = os.environ.get("SKAN_HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))
ALLOWED_ORIGINS = {origin.strip().rstrip("/") for origin in os.environ.get("SKAN_ALLOWED_ORIGINS", "").split(",") if origin.strip()}
REFRESH_LOCK = Lock()
REFRESH_STATE = {"status": "idle", "completed_sources": 0, "total_sources": 0, "videos_processed": 0, "current_source": "", "errors": []}
PUBLIC_FORM_LIMITS = {"feedback": (5, 3600), "donations": (3, 3600), "promotion_requests": (3, 3600)}


def send_owner_notification(subject: str, body: str) -> bool:
    """Send a server-side email; credentials are provided only through environment variables."""
    sender = os.environ.get("SKAN_SMTP_USER", "").strip()
    password = os.environ.get("SKAN_SMTP_PASSWORD", "")
    recipient = os.environ.get("SKAN_NOTIFICATION_EMAIL", "alesvmelo@gmail.com").strip()
    if not sender or not password:
        print(f"Aviso: e-mail não enviado ({subject}); configure SKAN_SMTP_USER e SKAN_SMTP_PASSWORD.")
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    try:
        host = os.environ.get("SKAN_SMTP_HOST", "smtp.gmail.com")
        port = int(os.environ.get("SKAN_SMTP_PORT", "587"))
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as server:
                server.login(sender, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.starttls(context=context)
                server.login(sender, password)
                server.send_message(message)
        return True
    except (OSError, smtplib.SMTPException, ValueError) as exc:
        print(f"Erro ao enviar notificação para {recipient}: {exc}")
        return False


def ensure_feedback_table():
    with connect_database(DATABASE_PATH) as connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS hunt_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id TEXT NOT NULL REFERENCES videos(video_id) ON DELETE CASCADE,
            nickname TEXT NOT NULL DEFAULT '',
            vocation TEXT NOT NULL,
            player_level INTEGER NOT NULL,
            tested INTEGER NOT NULL DEFAULT 1,
            outdated INTEGER NOT NULL DEFAULT 0,
            xp_raw TEXT NOT NULL DEFAULT '',
            profit TEXT NOT NULL DEFAULT '',
            difficulty INTEGER,
            result TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_hunt_feedback_video ON hunt_feedback(video_id, id DESC)")
        connection.execute("""CREATE TABLE IF NOT EXISTS public_form_submissions (
            form_name TEXT NOT NULL, client_key TEXT NOT NULL, submitted_at INTEGER NOT NULL
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_public_form_submissions ON public_form_submissions(form_name, client_key, submitted_at)")
        connection.execute("""CREATE TABLE IF NOT EXISTS tc_donations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nickname TEXT NOT NULL,
            amount_tc INTEGER NOT NULL, show_in_ranking INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TEXT
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS managed_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_type TEXT NOT NULL,
            source_key TEXT NOT NULL UNIQUE, name TEXT NOT NULL, vocation TEXT NOT NULL,
            source_url TEXT NOT NULL, promotion_status TEXT NOT NULL DEFAULT 'organic',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        connection.execute("""CREATE TABLE IF NOT EXISTS promotion_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT, creator_name TEXT NOT NULL,
            youtube_url TEXT NOT NULL, vocation TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        connection.execute("""INSERT OR IGNORE INTO managed_sources(source_type,source_key,name,vocation,source_url)
            SELECT CASE WHEN vocation='CHANNEL' THEN 'channel' ELSE 'playlist' END,
            playlist_id,name,vocation,playlist_url FROM playlists""")


def apply_manual_classification_overrides():
    """Apply confirmed exceptions to existing rows, including already-seeded Neon data."""
    with connect_database(DATABASE_PATH) as connection:
        for video_id, classification in MANUAL_OVERRIDES.items():
            connection.execute("""UPDATE videos SET
                hunt_type=?, players_count=?, needs_review=?, review_reason=?
                WHERE video_id=?""", (
                    classification.hunt_type,
                    classification.players_count,
                    int(classification.needs_review),
                    classification.review_reason or "",
                    video_id,
                ))


def refresh_static_catalog():
    """Keep the file:// version of the page in sync with the SQLite catalog."""
    ensure_feedback_table()
    with connect_database(DATABASE_PATH) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("""SELECT MIN(COALESCE(pv.position, v.position)) AS position,
            v.video_id, v.title, v.description, v.published_at, v.channel_title, v.video_url,
            v.hunt_type, v.players_count, v.needs_review, v.review_reason,
            v.xp_raw_per_hour, v.xp_raw_display, v.xp_source_display,
            v.xp_multiplier_percent, v.xp_raw_status, v.xp_raw_note,
            v.profit_per_hour, v.profit_display, v.profit_source_display, v.profit_assumption,
            group_concat(DISTINCT CASE WHEN p.vocation != 'CHANNEL' THEN p.vocation END) AS playlist_vocations,
            group_concat(DISTINCT p.name) AS playlist_names,
            MAX(CASE WHEN p.vocation='CHANNEL' THEN 1 ELSE 0 END) AS from_channel,
            MAX(CASE WHEN ms.promotion_status='sponsored' THEN 1 ELSE 0 END) AS sponsored
            FROM videos v
            LEFT JOIN playlist_videos pv ON pv.video_id=v.video_id
            LEFT JOIN playlists p ON p.playlist_id=pv.playlist_id
            LEFT JOIN managed_sources ms ON ms.source_key=pv.playlist_id
            GROUP BY v.video_id ORDER BY position""").fetchall()
    data = json.dumps([dict(row) for row in rows], ensure_ascii=False)
    (FRONTEND_DIR / "catalog-data.js").write_text(
        f"window.SKAN_CATALOG = {data};\n", encoding="utf-8"
    )


def refresh_sources_worker(sources: list[dict]):
    global REFRESH_STATE
    python = os.environ.get("PYTHON_EXECUTABLE") or sys.executable
    updated, videos, errors = 0, 0, []
    try:
        for index, source in enumerate(sources, start=1):
            with REFRESH_LOCK:
                REFRESH_STATE["completed_sources"] = index - 1
                REFRESH_STATE["current_source"] = source["name"]
            kind = source["source_type"]
            command = [python, "-m", "backend.import_youtube_playlist"]
            if kind == "channel":
                command += ["--channel", source["source_url"]]
            elif kind == "video":
                vocation = source["vocation"] if source["vocation"] in {"MS", "EK", "ED", "EM", "RP"} else "MS"
                command += ["--video", source["source_url"], "--vocation", vocation]
            else:
                vocation = source["vocation"] if source["vocation"] in {"MS", "EK", "ED", "EM", "RP"} else "MS"
                command += ["--playlist-id", source["source_url"], "--vocation", vocation, "--playlist-name", source["name"]]
            try:
                result = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600, env=os.environ.copy())
                if result.returncode:
                    errors.append({"source": source["name"], "error": (result.stderr or result.stdout)[-1200:]})
                else:
                    updated += 1
                    match = re.search(r"Vídeos extraídos:\s*(\d+)", result.stdout)
                    videos += int(match.group(1)) if match else 0
            except (OSError, subprocess.TimeoutExpired) as exc:
                errors.append({"source": source["name"], "error": str(exc)})
            with REFRESH_LOCK:
                REFRESH_STATE["completed_sources"] = index
                REFRESH_STATE["videos_processed"] = videos
                REFRESH_STATE["errors"] = errors.copy()
        refresh_static_catalog()
        with REFRESH_LOCK:
            REFRESH_STATE.update({"status": "completed", "updated_sources": updated, "videos_processed": videos, "errors": errors, "current_source": ""})
    except Exception as exc:
        with REFRESH_LOCK:
            REFRESH_STATE.update({"status": "failed", "error": str(exc), "errors": errors, "current_source": ""})


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/videos":
            self.send_catalog()
            return
        if path == "/api/feedback-counts":
            self.send_feedback_counts()
            return
        match = re.fullmatch(r"/api/videos/([^/]+)/feedback", path)
        if match:
            self.send_feedback(unquote(match.group(1)))
            return
        if path == "/api/donations/leaderboard":
            self.send_leaderboard()
            return
        if path in {"/api/admin/sources", "/api/admin/donations", "/api/admin/promotions", "/api/admin/sources/refresh/status"}:
            if not self.admin_authorized():
                self.send_json(401, {"error": "Acesso administrativo necessário."})
            elif path.endswith("sources"):
                self.send_admin_sources()
            elif path.endswith("promotions"):
                self.send_admin_promotions()
            elif path.endswith("status"):
                self.send_refresh_status()
            else:
                self.send_pending_donations()
            return
        if self.is_private_file(path):
            self.send_error(404)
            return
        super().do_GET()

    def do_OPTIONS(self):
        if not self._cors_origin():
            self.send_error(403, "Origem não permitida")
            return
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Skan-Admin-Key")
        self.send_header("Access-Control-Max-Age", "600")
        self.end_headers()

    def _cors_origin(self):
        origin = self.headers.get("Origin", "").rstrip("/")
        return origin if origin and origin in ALLOWED_ORIGINS else ""

    def _send_cors_headers(self):
        origin = self._cors_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def do_HEAD(self):
        if self.is_private_file(urlparse(self.path).path):
            self.send_error(404)
            return
        super().do_HEAD()

    @staticmethod
    def is_private_file(path: str) -> bool:
        # Check the decoded path: translate_path decodes before opening, so /README.%6dd must be blocked too.
        decoded = Path(unquote(path))
        return (
            decoded.suffix.lower() in {".py", ".pyc", ".md", ".db", ".csv", ".zip"}
            or any(part.startswith(".") or part == "__pycache__" for part in decoded.parts)
        )

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/donations":
            self.receive_donation()
            return
        if path == "/api/promotion-requests":
            self.receive_promotion_request()
            return
        if path == "/api/admin/sources":
            if not self.admin_authorized():
                self.send_json(401, {"error": "Acesso administrativo necessário."})
                return
            self.import_source()
            return
        if path == "/api/admin/sources/refresh":
            if not self.admin_authorized():
                self.send_json(401, {"error": "Acesso administrativo necessário."})
                return
            self.refresh_all_sources()
            return
        match = re.fullmatch(r"/api/admin/donations/(\d+)/confirm", path)
        if match:
            if not self.admin_authorized():
                self.send_json(401, {"error": "Acesso administrativo necessário."})
                return
            with connect_database(DATABASE_PATH) as connection:
                connection.execute("UPDATE tc_donations SET status='confirmed', confirmed_at=CURRENT_TIMESTAMP WHERE id=?", (int(match.group(1)),))
            self.send_json(200, {"message": "Contribuição confirmada."})
            return
        match = re.fullmatch(r"/api/admin/sources/(\d+)/promotion", path)
        if match:
            if not self.admin_authorized():
                self.send_json(401, {"error": "Acesso administrativo necessário."})
                return
            try:
                data = self.read_json_body()
                status = str(data.get("status", ""))
                if status not in {"organic", "sponsored"}:
                    raise ValueError("Estado de divulgação inválido.")
                with connect_database(DATABASE_PATH) as connection:
                    connection.execute("UPDATE managed_sources SET promotion_status=? WHERE id=?", (status, int(match.group(1))))
                refresh_static_catalog()
                self.send_json(200, {"message": "Divulgação atualizada."})
            except (ValueError, TypeError, json.JSONDecodeError, *DATABASE_ERRORS) as exc:
                self.send_json(400, {"error": str(exc)})
            return
        match = re.fullmatch(r"/api/videos/([^/]+)/feedback", urlparse(self.path).path)
        if not match:
            self.send_json(404, {"error": "Endereço não encontrado."})
            return
        video_id = unquote(match.group(1))
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 12_000:
                raise ValueError("O formulário excedeu o tamanho permitido.")
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Confira os campos informados.")
            if not self.allow_public_submission("feedback", data):
                return
            nickname = str(data.get("nickname", "")).strip()[:40]
            vocation = str(data.get("vocation", "")).strip().upper()
            level = int(data.get("player_level", 0))
            result = str(data.get("result", "")).strip()
            xp_raw = str(data.get("xp_raw", "")).strip()[:40]
            profit = str(data.get("profit", "")).strip()[:40]
            tested = bool(data.get("tested", True))
            outdated = bool(data.get("outdated", False))
            difficulty = data.get("difficulty")
            difficulty = int(difficulty) if difficulty not in (None, "") else None
            if vocation not in {"MS", "EK", "ED", "RP", "EM"}:
                raise ValueError("Selecione uma vocação válida.")
            if not 1 <= level <= 5000:
                raise ValueError("Informe um level entre 1 e 5000.")
            if len(result) < 8 or len(result) > 2000:
                raise ValueError("Conte o resultado em pelo menos 8 caracteres (máximo 2000).")
            if difficulty is not None and not 1 <= difficulty <= 5:
                raise ValueError("A dificuldade deve ficar entre 1 e 5.")
            with connect_database(DATABASE_PATH) as connection:
                exists = connection.execute("SELECT 1 FROM videos WHERE video_id=?", (video_id,)).fetchone()
                if not exists:
                    self.send_json(404, {"error": "Vídeo não encontrado."})
                    return
                connection.execute("""INSERT INTO hunt_feedback
                    (video_id,nickname,vocation,player_level,tested,outdated,xp_raw,profit,difficulty,result)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (video_id,nickname,vocation,level,int(tested),int(outdated),xp_raw,profit,difficulty,result))
                feedback_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
            self.send_json(201, {"id": feedback_id, "message": "Feedback registrado."})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc) or "Confira os campos informados."})
        except DATABASE_ERRORS:
            self.send_json(500, {"error": "Não foi possível salvar o feedback."})

    def do_DELETE(self):
        match = re.fullmatch(r"/api/admin/sources/(\d+)", urlparse(self.path).path)
        if not match:
            self.send_json(404, {"error": "Endereço não encontrado."})
            return
        if not self.admin_authorized():
            self.send_json(401, {"error": "Acesso administrativo necessário."})
            return
        source_id = int(match.group(1))
        with connect_database(DATABASE_PATH) as connection:
            connection.row_factory = sqlite3.Row
            source = connection.execute("SELECT * FROM managed_sources WHERE id=?", (source_id,)).fetchone()
            if not source:
                self.send_json(404, {"error": "Fonte não encontrada."})
                return
            source_key = source["source_key"]
            connection.execute("DELETE FROM playlist_videos WHERE playlist_id=?", (source_key,))
            connection.execute("DELETE FROM playlists WHERE playlist_id=?", (source_key,))
            connection.execute("DELETE FROM videos WHERE NOT EXISTS (SELECT 1 FROM playlist_videos pv WHERE pv.video_id=videos.video_id)")
            connection.execute("DELETE FROM managed_sources WHERE id=?", (source_id,))
        csv_path = DATABASE_PATH.parent / "playlist_videos.csv"
        if csv_path.exists():
            with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream); fields = reader.fieldnames; rows = list(reader)
            rows = [row for row in rows if row.get("playlist_id") != source_key]
            with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        manifest_path = DATABASE_PATH.parent / "playlist_manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["playlists"] = [item for item in manifest.get("playlists", []) if item.get("playlist_id") != source_key]
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        refresh_static_catalog()
        self.send_json(200, {"message": "Fonte e vídeos exclusivos removidos do catálogo."})

    def admin_authorized(self):
        configured = os.environ.get("SKAN_ADMIN_KEY", "")
        supplied = self.headers.get("X-Skan-Admin-Key", "")
        return bool(configured) and hmac.compare_digest(supplied, configured)

    def read_json_body(self):
        size = int(self.headers.get("Content-Length", "0"))
        if size < 1 or size > 12_000:
            raise ValueError("O formulário excedeu o tamanho permitido.")
        value = json.loads(self.rfile.read(size))
        if not isinstance(value, dict):
            raise ValueError("Confira os campos informados.")
        return value

    def allow_public_submission(self, form_name: str, data: dict) -> bool:
        """Apply a persistent per-IP sliding window and reject automated honeypot posts."""
        if str(data.get("website", "")).strip():
            self.send_json(400, {"error": "Não foi possível validar o formulário. Confira os dados e tente novamente."})
            return False
        limit, window = PUBLIC_FORM_LIMITS[form_name]
        address = self.client_address[0] if self.client_address else "unknown"
        # Only trust proxy headers when explicitly enabled. Use the last entry: the hosting proxy
        # appends the real client IP there, while earlier entries can be sent by the client.
        if os.environ.get("SKAN_TRUST_PROXY_HEADERS") == "1":
            forwarded = self.headers.get("X-Forwarded-For", "").rsplit(",", 1)[-1].strip()
            if forwarded:
                address = forwarded
        now = int(time.time())
        ensure_feedback_table()
        with connect_database(DATABASE_PATH) as connection:
            connection.execute("DELETE FROM public_form_submissions WHERE submitted_at < ?", (now - 86400,))
            count = connection.execute("SELECT COUNT(*) FROM public_form_submissions WHERE form_name=? AND client_key=? AND submitted_at>?", (form_name, address, now - window)).fetchone()[0]
            if count >= limit:
                self.send_json(429, {"error": "Você atingiu o limite de envios por enquanto. Aguarde um pouco e tente novamente."})
                return False
            connection.execute("INSERT INTO public_form_submissions(form_name,client_key,submitted_at) VALUES(?,?,?)", (form_name, address, now))
        return True

    def receive_donation(self):
        try:
            data = self.read_json_body()
            if not self.allow_public_submission("donations", data):
                return
            nickname = str(data.get("nickname", "")).strip()[:40]
            amount = int(data.get("amount_tc", 0))
            show = int(bool(data.get("show_in_ranking", False)))
            if not nickname or not 1 <= amount <= 10_000_000:
                raise ValueError("Informe seu apelido e uma quantidade de TC válida.")
            with connect_database(DATABASE_PATH) as connection:
                connection.execute("INSERT INTO tc_donations(nickname,amount_tc,show_in_ranking) VALUES (?,?,?)", (nickname,amount,show))
                donation_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
            notified = send_owner_notification(
                "Nova doação em Tibia Coins · Skan Coach",
                f"Nova contribuição registrada.\n\nPersonagem: {nickname}\nQuantidade informada: {amount:,} TC\nRanking público: {'sim' if show else 'não'}\nStatus: aguardando sua validação manual em Lord Skanzin — Jadebra.\nID do registro: {donation_id}",
            )
            message = "Contribuição registrada e aguardando sua validação manual."
            if not notified:
                message += " O site não conseguiu enviar o e-mail de aviso; confira as configurações de e-mail do servidor."
            self.send_json(201, {"id": donation_id, "message": message, "notification_sent": notified})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc) or "Confira os dados da contribuição."})

    def send_leaderboard(self):
        with connect_database(DATABASE_PATH) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("""SELECT nickname, SUM(amount_tc) AS total_tc
                FROM tc_donations WHERE status='confirmed' AND show_in_ranking=1
                GROUP BY nickname ORDER BY total_tc DESC, nickname LIMIT 20""").fetchall()
        self.send_json(200, [dict(row) for row in rows])

    def send_pending_donations(self):
        with connect_database(DATABASE_PATH) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT id,nickname,amount_tc,show_in_ranking,created_at FROM tc_donations WHERE status='pending' ORDER BY id").fetchall()
        self.send_json(200, [dict(row) for row in rows])

    def send_admin_sources(self):
        with connect_database(DATABASE_PATH) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute("SELECT id,source_type,source_key,name,vocation,source_url,promotion_status FROM managed_sources ORDER BY name").fetchall()
        self.send_json(200, [dict(row) for row in rows])

    def receive_promotion_request(self):
        try:
            data = self.read_json_body()
            if not self.allow_public_submission("promotion_requests", data):
                return
            creator = str(data.get("creator_name", "")).strip()[:80]
            url = str(data.get("youtube_url", "")).strip()[:300]
            vocation = str(data.get("vocation", "")).strip().upper()
            note = str(data.get("note", "")).strip()[:500]
            if not creator or not url.startswith(("https://youtube.com/", "https://www.youtube.com/", "https://youtu.be/")):
                raise ValueError("Informe seu nome/canal e um link válido do YouTube.")
            if vocation not in {"MS","EK","ED","EM","RP","CHANNEL"}:
                raise ValueError("Selecione uma vocação válida.")
            with connect_database(DATABASE_PATH) as connection:
                connection.execute("INSERT INTO promotion_requests(creator_name,youtube_url,vocation,note) VALUES (?,?,?,?)", (creator,url,vocation,note))
                request_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
            notified = send_owner_notification(
                "Novo pedido para divulgar uma hunt · Skan Coach",
                f"Novo pedido de divulgação recebido.\n\nCriador/canal: {creator}\nLink: {url}\nVocação: {vocation}\nObservação: {note or 'Nenhuma'}\nID do pedido: {request_id}\n\nEntre no Portal do Skan Coach para revisar e importar se aprovado.",
            )
            message = "Pedido recebido para análise."
            if not notified:
                message += " O site não conseguiu enviar o e-mail de aviso; confira as configurações de e-mail do servidor."
            self.send_json(201,{"message":message,"notification_sent":notified})
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self.send_json(400,{"error":str(exc)})

    def send_admin_promotions(self):
        with connect_database(DATABASE_PATH) as connection:
            connection.row_factory=sqlite3.Row
            rows=connection.execute("SELECT id,creator_name,youtube_url,vocation,note,created_at FROM promotion_requests WHERE status='pending' ORDER BY id").fetchall()
        self.send_json(200,[dict(row) for row in rows])

    def import_source(self):
        try:
            data = self.read_json_body()
            source_type = str(data.get("source_type", "")).strip().lower()
            source_url = str(data.get("source_url", "")).strip()
            name = str(data.get("name", "")).strip()[:100]
            vocation = str(data.get("vocation", "MS")).strip().upper()
            if source_type not in {"playlist", "channel", "video"} or not source_url:
                raise ValueError("Informe o link e selecione playlist, canal ou vídeo.")
            if source_type == "channel":
                vocation = "CHANNEL"
            elif vocation not in {"MS","EK","ED","RP","EM"}:
                raise ValueError("Selecione uma vocação válida.")
            if not os.environ.get("YOUTUBE_API_KEY"):
                raise ValueError("Configure YOUTUBE_API_KEY no servidor para importar vídeos.")
            command = [os.environ.get("PYTHON_EXECUTABLE") or sys.executable, "-m", "backend.import_youtube_playlist"]
            if source_type == "channel":
                command += ["--channel", source_url]
            elif source_type == "video":
                command += ["--video", source_url, "--vocation", vocation]
            else:
                command += ["--playlist-id", source_url, "--vocation", vocation, "--playlist-name", name or vocation]
            completed = subprocess.run(command, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600, env=os.environ.copy())
            if completed.returncode:
                raise RuntimeError((completed.stderr or completed.stdout)[-3000:])
            with connect_database(DATABASE_PATH) as connection:
                connection.row_factory = sqlite3.Row
                source = connection.execute("SELECT playlist_id,name,playlist_url FROM playlists WHERE playlist_url=? ORDER BY rowid DESC LIMIT 1", (source_url,)).fetchone()
                if not source:
                    source = connection.execute("SELECT playlist_id,name,playlist_url FROM playlists ORDER BY rowid DESC LIMIT 1").fetchone()
                if not source:
                    raise RuntimeError("Importação terminou sem registrar a fonte no catálogo.")
                source_name = name or source["name"]
                connection.execute("""INSERT INTO managed_sources(source_type,source_key,name,vocation,source_url)
                    VALUES(?,?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET
                    source_type=excluded.source_type,name=excluded.name,vocation=excluded.vocation,source_url=excluded.source_url""",
                    (source_type,source["playlist_id"],source_name,vocation,source_url))
                if source_type == "playlist":
                    manifest_path = DATABASE_PATH.parent / "playlist_manifest.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"playlists": []}
                    entries = manifest.setdefault("playlists", [])
                    entries[:] = [item for item in entries if item.get("playlist_id") != source["playlist_id"]]
                    entries.append({"playlist_id": source["playlist_id"], "vocation": vocation, "name": source_name})
                    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.send_json(201, {"message": "Fonte importada e adicionada ao catálogo.", "details": completed.stdout[-1500:]})
        except (ValueError, TypeError, json.JSONDecodeError, *DATABASE_ERRORS, subprocess.TimeoutExpired, RuntimeError) as exc:
            self.send_json(400, {"error": str(exc)})

    def refresh_all_sources(self):
        if not os.environ.get("YOUTUBE_API_KEY"):
            self.send_json(400, {"error": "Configure YOUTUBE_API_KEY e reinicie o servidor antes de atualizar."})
            return
        with connect_database(DATABASE_PATH) as connection:
            connection.row_factory = sqlite3.Row
            sources = connection.execute("SELECT source_type,source_url,name,vocation FROM managed_sources ORDER BY source_type,name").fetchall()
        if not sources:
            self.send_json(400, {"error": "Não há fontes cadastradas para atualizar."})
            return
        source_list = [dict(source) for source in sources]
        with REFRESH_LOCK:
            if REFRESH_STATE.get("status") == "running":
                self.send_json(202, dict(REFRESH_STATE))
                return
            REFRESH_STATE.clear()
            REFRESH_STATE.update({"status": "running", "completed_sources": 0, "total_sources": len(source_list), "videos_processed": 0, "current_source": "Preparando atualização…", "errors": []})
        Thread(target=refresh_sources_worker, args=(source_list,), daemon=True).start()
        self.send_json(202, dict(REFRESH_STATE))

    def send_refresh_status(self):
        with REFRESH_LOCK:
            state = dict(REFRESH_STATE)
        self.send_json(200, state)

    def send_feedback(self, video_id):
        try:
            with connect_database(DATABASE_PATH) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute("""SELECT id,nickname,vocation,player_level,tested,outdated,
                    xp_raw,profit,difficulty,result,created_at FROM hunt_feedback
                    WHERE video_id=? ORDER BY id DESC LIMIT 100""", (video_id,)).fetchall()
            self.send_json(200, [dict(row) for row in rows])
        except DATABASE_ERRORS:
            self.send_json(500, {"error": "Não foi possível carregar os feedbacks."})

    def send_feedback_counts(self):
        try:
            ensure_feedback_table()
            with connect_database(DATABASE_PATH) as connection:
                rows = connection.execute("SELECT video_id,COUNT(*) FROM hunt_feedback GROUP BY video_id").fetchall()
            self.send_json(200, {video_id: count for video_id, count in rows})
        except DATABASE_ERRORS:
            self.send_json(500, {"error": "Não foi possível carregar as contagens de feedback."})

    def send_json(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_catalog(self):
        try:
            ensure_feedback_table()
            with connect_database(DATABASE_PATH) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute("""SELECT MIN(COALESCE(pv.position, v.position)) AS position,
                    v.video_id, v.title, v.description, v.published_at, v.channel_title, v.video_url,
                    v.hunt_type, v.players_count, v.needs_review, v.review_reason,
                    v.xp_raw_per_hour, v.xp_raw_display, v.xp_source_display,
                    v.xp_multiplier_percent, v.xp_raw_status, v.xp_raw_note,
                    v.profit_per_hour, v.profit_display, v.profit_source_display, v.profit_assumption,
                    group_concat(DISTINCT CASE WHEN p.vocation != 'CHANNEL' THEN p.vocation END) AS playlist_vocations,
                    group_concat(DISTINCT p.name) AS playlist_names,
                    MAX(CASE WHEN p.vocation='CHANNEL' THEN 1 ELSE 0 END) AS from_channel,
                    MAX(CASE WHEN ms.promotion_status='sponsored' THEN 1 ELSE 0 END) AS sponsored
                    FROM videos v
                    LEFT JOIN playlist_videos pv ON pv.video_id=v.video_id
                    LEFT JOIN playlists p ON p.playlist_id=pv.playlist_id
                    LEFT JOIN managed_sources ms ON ms.source_key=pv.playlist_id
                    GROUP BY v.video_id ORDER BY position""").fetchall()
            body = json.dumps([dict(row) for row in rows], ensure_ascii=False).encode("utf-8")
        except (OSError, *DATABASE_ERRORS) as exc:
            # Database errors can include host/user details; keep them in the server log only.
            print(f"Erro ao carregar o catálogo: {exc}")
            body = json.dumps({"error": "Não foi possível carregar o catálogo."}, ensure_ascii=False).encode("utf-8")
            self.send_response(500)
        else:
            self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    if not DATABASE_PATH.exists():
        raise SystemExit(f"Banco não encontrado: {DATABASE_PATH}")
    if os.environ.get("DATABASE_URL"):
        initialize_postgres_catalog(DATABASE_PATH)
    apply_manual_classification_overrides()
    refresh_static_catalog()
    ensure_feedback_table()
    if os.environ.get("DATABASE_URL"):
        seed_postgres_community_data(DATABASE_PATH)
    print(f"Skan Coach disponível em http://{HOST}:{PORT}")
    print("Pressione Ctrl+C para encerrar.")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()

