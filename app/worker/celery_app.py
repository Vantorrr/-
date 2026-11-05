from datetime import timedelta

from celery import Celery
from celery.signals import worker_ready

from app.logging_setup import configure_logging
from app.settings import get_settings

configure_logging()
settings = get_settings()

celery_app = Celery("intake", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "fetch-listings": {
            "task": "intake.fetch_listings",
            "schedule": timedelta(minutes=max(5, int(settings.fetch_interval_minutes))),
        }
    },
)


@worker_ready.connect
def _on_ready(**_kwargs):
    from app.bootstrap import prepare_storage

    prepare_storage()


@celery_app.task(name="intake.fetch_listings")
def fetch_listings():
    from app.bootstrap import prepare_storage
    from app.pipeline import run_once
    from app.runtime import is_paused

    prepare_storage()
    if is_paused():
        return {"status": "paused"}
    return run_once()
