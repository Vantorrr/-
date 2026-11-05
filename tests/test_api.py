from fastapi.testclient import TestClient

from app.main import app
from app.settings import get_settings


def test_health_and_sources_do_not_claim_a_send():
    get_settings.cache_clear()
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        body = health.json()
        assert body["database"] == "ok"
        assert body["send_mode"] == "confirmation"
        sources = client.get("/api/sources")
        assert sources.status_code == 200
        enabled = {item["id"] for item in sources.json() if item["enabled"]}
        assert enabled == {"fl_ru", "habr_career", "workspace", "eis_zakupki"}
        profi = next(item for item in sources.json() if item["id"] == "profi_ru")
        assert profi["enabled"] is False
        assert "извлечение" in profi["reason"]
