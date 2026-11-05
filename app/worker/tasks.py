"""Celery tasks live in celery_app so the worker entrypoint stays one module."""

from app.worker.celery_app import fetch_listings

__all__ = ["fetch_listings"]
