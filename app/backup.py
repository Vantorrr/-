import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.logging_setup import configure_logging, get_logger
from app.settings import get_settings

log = get_logger("backup")


def parse_postgres_url(url: str) -> dict | None:
    if not (url or "").startswith("postgresql"):
        return None
    parsed = urlparse(url)
    database = (parsed.path or "").lstrip("/")
    if not parsed.hostname or not database:
        return None
    return {
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "host": parsed.hostname,
        "port": str(parsed.port or 5432),
        "database": database,
    }


def run_backup(database_url: str, dest_dir: Path, runner=None) -> int:
    parts = parse_postgres_url(database_url)
    if parts is None:
        log.info("backup_skipped", reason="not postgres; pg_dump was not run")
        return 2
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"intake-{stamp}.dump"
    env = os.environ.copy()
    env["PGPASSWORD"] = parts["password"]
    args = [
        "pg_dump",
        "-h",
        parts["host"],
        "-p",
        parts["port"],
        "-U",
        parts["user"],
        "-d",
        parts["database"],
        "-Fc",
        "-f",
        str(dest),
    ]
    completed = (runner or subprocess.run)(args, env=env, check=False)
    return int(completed.returncode)


def main() -> None:
    configure_logging()
    settings = get_settings()
    code = run_backup(settings.database_url, Path(settings.data_dir) / "backups")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
