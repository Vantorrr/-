from app.logging_setup import get_logger
from app.settings import get_settings

log = get_logger("runtime")
PAUSE_KEY = "intake:paused"
LOCK_KEY = "intake:lock"


def redis_client():
    settings = get_settings()
    try:
        import redis
    except ImportError:
        return None
    try:
        client = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=1)
        client.ping()
        return client
    except Exception as exc:
        log.info("redis_unavailable", error=str(exc))
        return None


def is_paused() -> bool:
    client = redis_client()
    if client is None:
        return False
    return client.get(PAUSE_KEY) == b"1"


def set_paused(paused: bool) -> bool:
    client = redis_client()
    if client is None:
        return False
    if paused:
        client.set(PAUSE_KEY, "1")
    else:
        client.delete(PAUSE_KEY)
    return True


def acquire_run_lock(ttl_seconds: int = 900) -> bool:
    client = redis_client()
    if client is None:
        return True
    return bool(client.set(LOCK_KEY, "1", nx=True, ex=ttl_seconds))


def release_run_lock() -> None:
    client = redis_client()
    if client is None:
        return
    client.delete(LOCK_KEY)
