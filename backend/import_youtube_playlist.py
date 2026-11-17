"""Download public playlist metadata from the YouTube Data API v3."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

from .title_classifier import HuntTitle, classify_hunt_title
from .profit_calculator import extract_profit
from .xp_calculator import calculate_raw_xp
from .database import DATABASE_ERRORS, connect_database


API_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
CHANNELS_API_URL = "https://www.googleapis.com/youtube/v3/channels"
VIDEOS_API_URL = "https://www.googleapis.com/youtube/v3/videos"
DEFAULT_PLAYLIST_ID = "PLOF-eZpj5a6mms9h0W5hC7eWNs6omp4PW"
SUPPORTED_VOCATIONS = {"MS", "EK", "ED", "RP", "EM"}
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data"
MANIFEST_PATH = OUTPUT_DIR / "playlist_manifest.json"
CSV_PATH = OUTPUT_DIR / "playlist_videos.csv"
DB_PATH = OUTPUT_DIR / "skan_coach.db"
CSV_COLUMNS = (
    "playlist_id", "playlist_vocation", "playlist_name", "playlist_url",
    "position", "video_id", "title", "description", "published_at",
    "channel_title", "video_url", "hunt_type", "players_count",
    "needs_review", "review_reason",
    "xp_raw_per_hour", "xp_raw_display", "xp_source_display",
    "xp_multiplier_percent", "xp_raw_status", "xp_raw_note",
    "profit_per_hour", "profit_display", "profit_source_display", "profit_assumption",
)
MANUAL_OVERRIDES = {
    # Manually confirmed as Solo by the user after reviewing the extracted titles.
    "Y5aTqA8NC7U": HuntTitle("Solo", 1, False),
    "z6kueqPT1NQ": HuntTitle("Solo", 1, False),
}


def classify_video_title(video_id: str, title: str, description: str = "") -> HuntTitle:
    return MANUAL_OVERRIDES.get(video_id) or classify_hunt_title(title, description)


def playlist_id_from(value: str) -> str:
    if "list=" in value:
        return parse_qs(urlparse(value).query).get("list", [""])[0]
    return value.strip()


def load_playlist_manifest(path: Path = MANIFEST_PATH) -> list[dict]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    playlists = manifest.get("playlists", [])
    if not playlists:
        raise ValueError("O manifesto não contém playlists.")
    for playlist in playlists:
        playlist["playlist_id"] = playlist_id_from(playlist.get("playlist_id", ""))
        playlist["vocation"] = playlist.get("vocation", "").upper()
        if not playlist["playlist_id"]:
            raise ValueError("Há uma playlist sem ID válido no manifesto.")
        if playlist["vocation"] not in SUPPORTED_VOCATIONS:
            raise ValueError(f"Vocação inválida no manifesto: {playlist['vocation']}")
        playlist.setdefault("name", playlist["vocation"])
        playlist.setdefault("playlist_url", f"https://www.youtube.com/playlist?list={playlist['playlist_id']}")
    return playlists


def request_playlist_page(api_key: str, playlist_id: str, page_token: str | None = None) -> dict:
    params = {
        "part": "snippet,contentDetails",
        "playlistId": playlist_id,
        "maxResults": 50,
        "key": api_key,
    }
    if page_token:
        params["pageToken"] = page_token
    request_url = f"{API_URL}?{urlencode(params)}"
    try:
        with urlopen(request_url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            message = detail.get("error", {}).get("message", str(exc))
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = str(exc)
        raise RuntimeError(f"YouTube API retornou HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise RuntimeError(f"Não foi possível conectar à YouTube API: {exc.reason}") from exc


def request_channel(api_key: str, params: dict) -> dict:
    request_url = f"{CHANNELS_API_URL}?{urlencode({**params, 'part': 'snippet,contentDetails', 'key': api_key})}"
    try:
        with urlopen(request_url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            message = detail.get("error", {}).get("message", str(exc))
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = str(exc)
        raise RuntimeError(f"YouTube API retornou HTTP {exc.code}: {message}") from exc
    except URLError as exc:
        raise RuntimeError(f"Não foi possível conectar à YouTube API: {exc.reason}") from exc


def request_video(api_key: str, video_id: str) -> dict:
    request_url = f"{VIDEOS_API_URL}?{urlencode({'part': 'snippet', 'id': video_id, 'key': api_key})}"
    try:
        with urlopen(request_url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Não foi possível consultar o vídeo no YouTube: {exc}") from exc


def video_id_from(value: str) -> str:
    parsed = urlparse(value)
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/").split("/")[0]
    if parsed.hostname and parsed.hostname.endswith("youtube.com"):
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [""])[0]
        segments = [part for part in parsed.path.split("/") if part]
        if len(segments) > 1 and segments[0] in {"shorts", "live", "embed"}:
            return segments[1]
    return value.strip()


def fetch_single_video(api_key: str, value: str, vocation: str = "MS") -> list[dict]:
    video_id = video_id_from(value)
    item = next(iter(request_video(api_key, video_id).get("items", [])), None)
    if not item:
        raise ValueError("Vídeo não encontrado ou não está público.")
    snippet = item.get("snippet") or {}
    title, description = snippet.get("title", ""), snippet.get("description", "")
    if not is_hunt_candidate(title):
        raise ValueError("O título precisa conter XP numérica ou valor numérico de Profit/Waste.")
    classification = classify_video_title(video_id, title, description)
    xp, profit = calculate_raw_xp(title), extract_profit(title)
    source_key = f"video:{video_id}"
    return [{
        "playlist_id": source_key, "playlist_vocation": vocation,
        "playlist_name": f"Vídeo · {snippet.get('channelTitle') or video_id}",
        "playlist_url": value, "position": 0, "video_id": video_id,
        "title": title, "description": description, "published_at": snippet.get("publishedAt", ""),
        "channel_title": snippet.get("channelTitle", ""), "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "hunt_type": classification.hunt_type, "players_count": classification.players_count,
        "needs_review": int(classification.needs_review), "review_reason": classification.review_reason or "",
        "xp_raw_per_hour": xp.raw_value, "xp_raw_display": xp.raw_display or "",
        "xp_source_display": xp.source_display or "", "xp_multiplier_percent": xp.multiplier_percent,
        "xp_raw_status": xp.status, "xp_raw_note": xp.note or "",
        "profit_per_hour": profit.value_per_hour, "profit_display": profit.display or "",
        "profit_source_display": profit.source_display or "", "profit_assumption": profit.assumption or "",
    }]


def resolve_channel(api_key: str, value: str) -> dict:
    """Resolve a channel URL, UC id, or @handle and returns its uploads list."""
    parsed = urlparse(value if "://" in value else f"https://www.youtube.com/{value.lstrip('/')}")
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        raise ValueError("Informe o link do canal, o ID UC... ou @handle.")
    first = segments[0]
    if first == "channel" and len(segments) > 1:
        query = {"id": segments[1]}
    elif first.startswith("@"):
        query = {"forHandle": first}
    elif first == "user" and len(segments) > 1:
        query = {"forUsername": segments[1]}
    elif first.startswith("UC"):
        query = {"id": first}
    elif value.startswith("UC"):
        query = {"id": value.strip()}
    elif value.startswith("@"):
        query = {"forHandle": value.strip()}
    else:
        raise ValueError("Link de canal não reconhecido. Use youtube.com/@nome ou youtube.com/channel/UC...")
    items = request_channel(api_key, query).get("items", [])
    if not items:
        raise ValueError("Canal não encontrado ou não acessível pela API.")
    item = items[0]
    snippet = item.get("snippet") or {}
    uploads_id = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
    if not uploads_id:
        raise ValueError("Não foi possível encontrar a lista de vídeos enviados pelo canal.")
    return {"channel_id": item["id"], "name": snippet.get("title") or item["id"], "uploads_id": uploads_id}


def is_hunt_candidate(title: str) -> bool:
    """Keep channel videos that expose a numeric XP rate or numeric Profit."""
    return calculate_raw_xp(title).status != "not_found" or extract_profit(title).value_per_hour is not None


def merge_csv_rows(new_rows: list[dict], path: Path = CSV_PATH) -> list[dict]:
    """Add a new source to the CSV without dropping already imported sources."""
    old_rows = []
    if path.exists():
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            old_rows = list(csv.DictReader(csv_file))
    refreshed_sources = {row.get("playlist_id") for row in new_rows}
    old_rows = [row for row in old_rows if row.get("playlist_id") not in refreshed_sources]
    combined = {(row.get("playlist_id"), row.get("video_id")): row for row in old_rows}
    combined.update({(row.get("playlist_id"), row.get("video_id")): row for row in new_rows})
    rows = list(combined.values())
    write_csv(rows, path)
    return rows


def fetch_playlist(
    api_key: str,
    playlist_id: str,
    playlist_vocation: str = "MS",
    playlist_name: str = "Master Sorcerer",
    playlist_url: str | None = None,
) -> list[dict]:
    rows: list[dict] = []
    page_token = None
    while True:
        payload = request_playlist_page(api_key, playlist_id, page_token)
        for item in payload.get("items", []):
            snippet = item.get("snippet") or {}
            details = item.get("contentDetails") or {}
            resource = snippet.get("resourceId") or {}
            video_id = resource.get("videoId") or details.get("videoId")
            # YouTube can leave unavailable/private/deleted entries in a list.
            if not video_id:
                continue
            title = snippet.get("title", "")
            description = snippet.get("description", "")
            classification = classify_video_title(video_id, title, description)
            xp = calculate_raw_xp(title)
            profit = extract_profit(title)
            rows.append({
                "playlist_id": playlist_id,
                "playlist_vocation": playlist_vocation,
                "playlist_name": playlist_name,
                "playlist_url": playlist_url or f"https://www.youtube.com/playlist?list={playlist_id}",
                "position": snippet.get("position"),
                "video_id": video_id,
                "title": title,
                "description": description,
                "published_at": snippet.get("publishedAt", ""),
                "channel_title": snippet.get("videoOwnerChannelTitle") or snippet.get("channelTitle", ""),
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
                "hunt_type": classification.hunt_type,
                "players_count": classification.players_count,
                "needs_review": int(classification.needs_review),
                "review_reason": classification.review_reason or "",
                "xp_raw_per_hour": xp.raw_value,
                "xp_raw_display": xp.raw_display or "",
                "xp_source_display": xp.source_display or "",
                "xp_multiplier_percent": xp.multiplier_percent,
                "xp_raw_status": xp.status,
                "xp_raw_note": xp.note or "",
                "profit_per_hour": profit.value_per_hour,
                "profit_display": profit.display or "",
                "profit_source_display": profit.source_display or "",
                "profit_assumption": profit.assumption or "",
            })
        page_token = payload.get("nextPageToken")
        if not page_token:
            break
    return rows


def write_csv(rows: list[dict], path: Path = CSV_PATH) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def video_columns(connection) -> set[str]:
    if os.environ.get("DATABASE_URL"):
        return {row[0] for row in connection.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='videos'"
        )}
    return {row[1] for row in connection.execute("PRAGMA table_info(videos)")}


def upsert_playlist_metadata(connection: sqlite3.Connection, rows: list[dict]) -> None:
    connection.execute("""CREATE TABLE IF NOT EXISTS playlists (
        playlist_id TEXT PRIMARY KEY,
        vocation TEXT NOT NULL,
        name TEXT NOT NULL,
        playlist_url TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS playlist_videos (
        playlist_id TEXT NOT NULL,
        video_id TEXT NOT NULL,
        position INTEGER,
        PRIMARY KEY (playlist_id, video_id)
    )""")
    playlists = {}
    for row in rows:
        playlist_id = row.get("playlist_id") or DEFAULT_PLAYLIST_ID
        vocation = row.get("playlist_vocation") or "MS"
        name = row.get("playlist_name") or "Master Sorcerer"
        playlist_url = row.get("playlist_url") or f"https://www.youtube.com/playlist?list={playlist_id}"
        playlists[playlist_id] = (playlist_id, vocation, name, playlist_url)
    connection.executemany(
        "DELETE FROM playlist_videos WHERE playlist_id=?",
        [(playlist_id,) for playlist_id in playlists],
    )
    connection.executemany("""INSERT INTO playlists (playlist_id, vocation, name, playlist_url)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(playlist_id) DO UPDATE SET
            vocation=excluded.vocation, name=excluded.name, playlist_url=excluded.playlist_url
    """, list(playlists.values()))
    connection.executemany("""INSERT INTO playlist_videos (playlist_id, video_id, position)
        VALUES (:playlist_id, :video_id, :position)
        ON CONFLICT(playlist_id, video_id) DO UPDATE SET position=excluded.position
    """, rows)
    connection.execute("""DELETE FROM videos WHERE NOT EXISTS (
        SELECT 1 FROM playlist_videos pv WHERE pv.video_id=videos.video_id
    )""")


def write_sqlite(rows: list[dict], path: Path = DB_PATH) -> None:
    with closing(connect_database(path)) as connection, connection:
        connection.execute("""CREATE TABLE IF NOT EXISTS videos (
            video_id TEXT PRIMARY KEY,
            position INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            published_at TEXT,
            channel_title TEXT,
            video_url TEXT NOT NULL,
            hunt_type TEXT,
            players_count INTEGER,
            needs_review INTEGER NOT NULL DEFAULT 0,
            review_reason TEXT,
            xp_raw_per_hour REAL,
            xp_raw_display TEXT,
            xp_source_display TEXT,
            xp_multiplier_percent REAL,
            xp_raw_status TEXT,
            xp_raw_note TEXT,
            profit_per_hour REAL,
            profit_display TEXT,
            profit_source_display TEXT,
            profit_assumption TEXT
        )""")
        existing_columns = video_columns(connection)
        for name, sql_type in (
            ("xp_raw_per_hour", "REAL"),
            ("xp_raw_display", "TEXT"),
            ("xp_source_display", "TEXT"),
            ("xp_multiplier_percent", "REAL"),
            ("xp_raw_status", "TEXT"),
            ("xp_raw_note", "TEXT"),
            ("profit_per_hour", "REAL"),
            ("profit_display", "TEXT"),
            ("profit_source_display", "TEXT"),
            ("profit_assumption", "TEXT"),
        ):
            if name not in existing_columns:
                connection.execute(f"ALTER TABLE videos ADD COLUMN {name} {sql_type}")
        connection.executemany("""INSERT INTO videos (
            position, video_id, title, description, published_at,
            channel_title, video_url, hunt_type, players_count,
            needs_review, review_reason, xp_raw_per_hour, xp_raw_display,
            xp_source_display, xp_multiplier_percent, xp_raw_status, xp_raw_note,
            profit_per_hour, profit_display, profit_source_display, profit_assumption
        ) VALUES (
            :position, :video_id, :title, :description, :published_at,
            :channel_title, :video_url, :hunt_type, :players_count,
            :needs_review, :review_reason, :xp_raw_per_hour, :xp_raw_display,
            :xp_source_display, :xp_multiplier_percent, :xp_raw_status, :xp_raw_note,
            :profit_per_hour, :profit_display, :profit_source_display, :profit_assumption
        ) ON CONFLICT(video_id) DO UPDATE SET
            position=excluded.position,
            title=excluded.title,
            description=excluded.description,
            published_at=excluded.published_at,
            channel_title=excluded.channel_title,
            video_url=excluded.video_url,
            hunt_type=excluded.hunt_type,
            players_count=excluded.players_count,
            needs_review=excluded.needs_review,
            review_reason=excluded.review_reason,
            xp_raw_per_hour=excluded.xp_raw_per_hour,
            xp_raw_display=excluded.xp_raw_display,
            xp_source_display=excluded.xp_source_display,
            xp_multiplier_percent=excluded.xp_multiplier_percent,
            xp_raw_status=excluded.xp_raw_status,
            xp_raw_note=excluded.xp_raw_note,
            profit_per_hour=excluded.profit_per_hour,
            profit_display=excluded.profit_display,
            profit_source_display=excluded.profit_source_display,
            profit_assumption=excluded.profit_assumption
        """, rows)
        upsert_playlist_metadata(connection, rows)


def reclassify_existing(csv_path: Path = CSV_PATH, db_path: Path = DB_PATH) -> list[dict]:
    """Reapply title rules to downloaded files without making API requests."""
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV não encontrado: {csv_path}")
    with csv_path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        rows = list(csv.DictReader(csv_file))
    for row in rows:
        row["playlist_id"] = row.get("playlist_id") or DEFAULT_PLAYLIST_ID
        row["playlist_vocation"] = row.get("playlist_vocation") or "MS"
        row["playlist_name"] = row.get("playlist_name") or "Master Sorcerer"
        row["playlist_url"] = row.get("playlist_url") or f"https://www.youtube.com/playlist?list={row['playlist_id']}"
        result = classify_video_title(
            row.get("video_id", ""), row.get("title", ""), row.get("description", "")
        )
        xp = calculate_raw_xp(row.get("title", ""))
        profit = extract_profit(row.get("title", ""))
        row.update({
            "hunt_type": result.hunt_type or "",
            "players_count": result.players_count or "",
            "needs_review": int(result.needs_review),
            "review_reason": result.review_reason or "",
            "xp_raw_per_hour": xp.raw_value,
            "xp_raw_display": xp.raw_display or "",
            "xp_source_display": xp.source_display or "",
            "xp_multiplier_percent": xp.multiplier_percent,
            "xp_raw_status": xp.status,
            "xp_raw_note": xp.note or "",
            "profit_per_hour": profit.value_per_hour,
            "profit_display": profit.display or "",
            "profit_source_display": profit.source_display or "",
            "profit_assumption": profit.assumption or "",
        })
    write_csv(rows, csv_path)
    if db_path.exists():
        with closing(connect_database(db_path)) as connection, connection:
            existing_columns = video_columns(connection)
            for name, sql_type in (
                ("xp_raw_per_hour", "REAL"),
                ("xp_raw_display", "TEXT"),
                ("xp_source_display", "TEXT"),
                ("xp_multiplier_percent", "REAL"),
                ("xp_raw_status", "TEXT"),
                ("xp_raw_note", "TEXT"),
                ("profit_per_hour", "REAL"),
                ("profit_display", "TEXT"),
                ("profit_source_display", "TEXT"),
                ("profit_assumption", "TEXT"),
            ):
                if name not in existing_columns:
                    connection.execute(f"ALTER TABLE videos ADD COLUMN {name} {sql_type}")
            connection.executemany("""UPDATE videos SET
                hunt_type=:hunt_type,
                players_count=:players_count,
                needs_review=:needs_review,
                review_reason=:review_reason,
                xp_raw_per_hour=:xp_raw_per_hour,
                xp_raw_display=:xp_raw_display,
                xp_source_display=:xp_source_display,
                xp_multiplier_percent=:xp_multiplier_percent,
                xp_raw_status=:xp_raw_status,
                xp_raw_note=:xp_raw_note,
                profit_per_hour=:profit_per_hour,
                profit_display=:profit_display,
                profit_source_display=:profit_source_display,
                profit_assumption=:profit_assumption
                WHERE video_id=:video_id
            """, rows)
            upsert_playlist_metadata(connection, rows)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrai títulos e metadados públicos de uma playlist do YouTube.")
    parser.add_argument("--playlist-id", default=DEFAULT_PLAYLIST_ID, help="ID da playlist (ou URL completa do YouTube)")
    parser.add_argument("--channel", help="Link do canal, ID UC... ou @handle; importa apenas títulos com XP/Profit numérico")
    parser.add_argument("--video", help="URL ou ID de um vídeo individual de hunt")
    parser.add_argument("--vocation", choices=sorted(SUPPORTED_VOCATIONS), default="MS",
                        help="Vocação associada à playlist quando importar uma lista isolada")
    parser.add_argument("--playlist-name", help="Nome da playlist quando importar uma lista isolada")
    parser.add_argument("--sync-config", action="store_true",
                        help="Importa todas as playlists registradas em playlist_manifest.json")
    parser.add_argument("--format", choices=("both", "csv", "sqlite"), default="both", help="Formatos a salvar")
    parser.add_argument("--reclassify-existing", action="store_true",
                        help="Reclassifica CSV/SQLite existentes sem consultar a API")
    args = parser.parse_args()

    if args.reclassify_existing:
        try:
            rows = reclassify_existing()
        except (OSError, *DATABASE_ERRORS) as exc:
            print(f"Erro ao reclassificar os arquivos: {exc}", file=sys.stderr)
            return 1
        print(f"CSV atualizado: {CSV_PATH}")
        if DB_PATH.exists():
            print(f"Banco SQLite atualizado: {DB_PATH}")
        print(f"Vídeos reclassificados: {len(rows)}")
        print(f"Marcados para revisão: {sum(int(row['needs_review']) for row in rows)}")
        return 0

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("Erro: defina YOUTUBE_API_KEY nesta janela do PowerShell.", file=sys.stderr)
        return 2

    channel_mode = bool(args.channel)
    video_mode = bool(args.video)
    if sum((bool(args.sync_config), channel_mode, video_mode)) > 1:
        print("Erro: use apenas um entre --channel, --video e --sync-config.", file=sys.stderr)
        return 2
    if args.sync_config:
        try:
            playlist_configs = load_playlist_manifest()
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"Erro na configuração das playlists: {exc}", file=sys.stderr)
            return 2
    elif video_mode:
        playlist_configs = []
    elif channel_mode:
        try:
            channel = resolve_channel(api_key, args.channel)
        except (RuntimeError, ValueError) as exc:
            print(f"Erro ao localizar o canal: {exc}", file=sys.stderr)
            return 1
        playlist_configs = [{
            "playlist_id": channel["uploads_id"],
            "vocation": "CHANNEL",
            "name": channel["name"],
            "playlist_url": args.channel,
        }]
    else:
        playlist_id = playlist_id_from(args.playlist_id)
        if not playlist_id:
            print("Erro: não consegui identificar o ID da playlist.", file=sys.stderr)
            return 2
        playlist_configs = [{
            "playlist_id": playlist_id,
            "vocation": args.vocation,
            "name": args.playlist_name or args.vocation,
            "playlist_url": args.playlist_id if "list=" in args.playlist_id else f"https://www.youtube.com/playlist?list={playlist_id}",
        }]
    if not playlist_configs and not video_mode:
        print("Erro: não consegui identificar o ID da playlist.", file=sys.stderr)
        return 2

    try:
        rows = []
        if video_mode:
            rows = fetch_single_video(api_key, args.video, args.vocation)
            print(f"Vídeo individual importado: {len(rows)}")
        for config in playlist_configs:
            label = "canal" if channel_mode else config["vocation"]
            print(f"Importando {config['name']} ({label})...")
            source_rows = fetch_playlist(
                api_key,
                config["playlist_id"],
                config["vocation"],
                config["name"],
                config["playlist_url"],
            )
            if channel_mode:
                source_rows = [row for row in source_rows if is_hunt_candidate(row["title"])]
                print(f"Vídeos com XP/Profit numérico no título: {len(source_rows)}")
            rows.extend(source_rows)
    except (RuntimeError, ValueError) as exc:
        print(f"Erro na extração: {exc}", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.format in ("both", "csv"):
        merge_csv_rows(rows)
        print(f"CSV salvo: {CSV_PATH}")
    if args.format in ("both", "sqlite"):
        write_sqlite(rows)
        print(f"Banco SQLite salvo: {DB_PATH}")
        try:
            from .app import refresh_static_catalog
            refresh_static_catalog()
            print("Catálogo da interface atualizado.")
        except (ImportError, OSError, *DATABASE_ERRORS) as exc:
            print(f"Aviso: não foi possível atualizar o catálogo da interface: {exc}", file=sys.stderr)
    print(f"Vídeos extraídos: {len(rows)}")
    print(f"Marcados para revisão: {sum(row['needs_review'] for row in rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
