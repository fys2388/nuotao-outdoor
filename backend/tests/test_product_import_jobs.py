"""Tests for Redis-backed product import background jobs."""

import json

import pytest

from app.core.redis import get_redis
from app.services import product_import_job_service


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        _ = ex
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)


@pytest.mark.asyncio
async def test_create_job_persists_pending_state(monkeypatch) -> None:
    redis = FakeRedis()
    scheduled: list[str] = []
    monkeypatch.setattr(
        product_import_job_service,
        "_schedule_job",
        lambda _redis, job_id: scheduled.append(job_id),
    )

    job = await product_import_job_service.create_job(
        redis,
        url_or_id="https://detail.1688.com/offer/1075485124628.html",
        temperature=0.3,
        max_tokens=2000,
    )

    stored = json.loads(redis.values[product_import_job_service._job_key(job["job_id"])])
    assert stored["status"] == "pending"
    assert stored["url_or_id"] == "https://detail.1688.com/offer/1075485124628.html"
    assert scheduled == [job["job_id"]]


@pytest.mark.asyncio
async def test_run_job_stores_real_result(monkeypatch) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(
        product_import_job_service,
        "_schedule_job",
        lambda _redis, _job_id: None,
    )

    async def fake_import(*_args, **_kwargs):
        return {
            "success": True,
            "data": {
                "product_id": "1075485124628",
                "data_source": "newton_agent",
                "product_info": {"name": "户外防水露营灯"},
                "ai_recognition": {"product_category": "户外照明"},
                "product_report": {"product_name": "户外防水露营灯"},
            },
            "error": None,
        }

    monkeypatch.setattr(
        product_import_job_service,
        "import_and_analyze_from_1688",
        fake_import,
    )
    job = await product_import_job_service.create_job(
        redis,
        url_or_id="https://detail.1688.com/offer/1075485124628.html",
        temperature=0.3,
        max_tokens=2000,
    )

    await product_import_job_service._run_job(redis, job["job_id"])

    stored = await product_import_job_service.get_job(redis, job["job_id"])
    assert stored is not None
    assert stored["status"] == "succeeded"
    assert stored["data"]["data_source"] == "newton_agent"
    assert stored["data"]["product_report"]["product_name"] == "户外防水露营灯"


def test_job_endpoints_submit_and_poll(api_client, monkeypatch) -> None:
    redis = FakeRedis()
    api_client.app.dependency_overrides[get_redis] = lambda: redis

    async def fake_create_job(_redis, **_kwargs):
        return {"job_id": "job-1", "status": "pending"}

    async def fake_get_job(_redis, _job_id):
        return {
            "job_id": "job-1",
            "status": "succeeded",
            "data": {
                "product_id": "1075485124628",
                "data_source": "newton_agent",
                "product_info": {"name": "户外防水露营灯"},
                "ai_recognition": {},
                "product_report": {},
            },
            "error": None,
        }

    monkeypatch.setattr(product_import_job_service, "create_job", fake_create_job)
    monkeypatch.setattr(product_import_job_service, "get_job", fake_get_job)

    created = api_client.post(
        "/api/v1/product-pipeline/import-and-analyze-1688/jobs",
        json={"url_or_id": "https://detail.1688.com/offer/1075485124628.html"},
    )
    assert created.status_code == 202
    assert created.json()["data"]["job_id"] == "job-1"

    polled = api_client.get(
        "/api/v1/product-pipeline/import-and-analyze-1688/jobs/job-1"
    )
    assert polled.status_code == 200
    assert polled.json()["data"]["status"] == "succeeded"
    assert polled.json()["data"]["data"]["data_source"] == "newton_agent"

    api_client.app.dependency_overrides.pop(get_redis, None)
