"""Generate a browser-readable catalog file from the adjacent SQLite database."""

from app import DATABASE_PATH, INTERFACE_DIR, refresh_static_catalog


if __name__ == "__main__":
    if not DATABASE_PATH.exists():
        raise SystemExit(f"Banco não encontrado: {DATABASE_PATH}")
    refresh_static_catalog()
    print(f"Catálogo estático atualizado: {INTERFACE_DIR / 'catalog-data.js'}")
