"""Celery tasks live in celery_app so the worker entrypoint stays one module."""

from app.worker.celery_app import daily_digest, fetch_listings

__all__ = ["daily_digest", "fetch_listings"]
