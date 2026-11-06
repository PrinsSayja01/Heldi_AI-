from __future__ import annotations

import json
import requests
from . import config


class QueueUnavailable(RuntimeError):
    pass


def _command(command: list[str]):
    if not config.REDIS_URL or not config.REDIS_TOKEN:
        raise QueueUnavailable("Durable research queue is not configured")
    response = requests.post(
        config.REDIS_URL,
        headers={"Authorization": f"Bearer {config.REDIS_TOKEN}"},
        json=command,
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("result")


def enqueue(job_id: str, city: str, country: str, max_companies: int, keywords: list[str], use_local_model: bool) -> None:
    _command(["RPUSH", config.QUEUE_KEY, json.dumps({
        "job_id": job_id, "city": city, "country": country,
        "max_companies": max_companies, "keywords": keywords,
        "use_local_model": use_local_model,
    })])


def dequeue(timeout: int = 20) -> dict | None:
    result = _command(["BLPOP", config.QUEUE_KEY, str(timeout)])
    if not result:
        return None
    return json.loads(result[1])