import time
from urllib.parse import urlparse

import httpx

from app.logging_setup import get_logger

log = get_logger("http")


class FetchError(Exception):
    pass


class PoliteClient:
    """One shared client per run: pause between calls to the same host, retry 429 and 5xx."""

    def __init__(self, *, user_agent: str, timeout: float, min_interval: float, max_retries: int):
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self._last: dict[str, float] = {}
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": user_agent,
                "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.1",
            },
        )

    def close(self) -> None:
        self._client.close()

    def _wait(self, host: str, minimum: float | None = None) -> None:
        gap = self.min_interval if minimum is None else max(self.min_interval, minimum)
        previous = self._last.get(host)
        if previous is not None:
            delay = gap - (time.monotonic() - previous)
            if delay > 0:
                time.sleep(delay)
        self._last[host] = time.monotonic()

    def get(self, url: str, *, timeout: float | None = None, min_interval: float | None = None) -> httpx.Response:
        host = urlparse(url).netloc
        last_error = "no response"
        for attempt in range(self.max_retries):
            self._wait(host, min_interval)
            try:
                response = self._client.get(url, timeout=timeout or self.timeout)
            except httpx.HTTPError as exc:
                last_error = str(exc)
                log.warning("http_error", host=host, attempt=attempt + 1, error=last_error)
                time.sleep(min(8, 2**attempt))
                continue
            log.info("http_response", host=host, status=response.status_code, attempt=attempt + 1)
            if response.status_code in {429, 500, 502, 503, 504}:
                last_error = f"HTTP {response.status_code}"
                retry_after = _retry_after(response.headers.get("Retry-After"))
                if retry_after is not None and retry_after > 30:
                    raise FetchError(f"{last_error}; Retry-After {retry_after}s exceeds 30s")
                time.sleep(retry_after if retry_after is not None else min(8, 2**attempt))
                continue
            final = str(response.url)
            if "/login" in final or "/auth" in final:
                raise FetchError(f"redirected to a login wall: {final}")
            return response
        raise FetchError(last_error)


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
