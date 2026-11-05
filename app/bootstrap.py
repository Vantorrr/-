from pathlib import Path

from app.db import init_db, init_engine
from app.settings import get_settings


def prepare_storage() -> None:
    settings = get_settings()
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        raw = settings.database_url.removeprefix("sqlite:///")
        if raw not in {":memory:", ""} and not raw.startswith(":memory:"):
            Path(raw).parent.mkdir(parents=True, exist_ok=True)
    init_engine(settings.database_url)
    init_db()
