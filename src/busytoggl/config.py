from __future__ import annotations

import os
from dataclasses import dataclass


def _positive_number(name: str, value: str, *, integer: bool = False) -> int | float:
    try:
        number = int(value) if integer else float(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if number <= 0:
        raise ValueError(f"{name} must be positive")
    return number


@dataclass(frozen=True)
class Config:
    busy_url: str
    busy_api_token: str | None
    toggl_api_token: str
    toggl_workspace_id: int
    poll_interval: float
    toggl_sync_interval: float
    toggl_hourly_limit: int
    request_timeout: float

    @classmethod
    def from_env(cls) -> "Config":
        token = os.getenv("TOGGL_API_TOKEN", "").strip()
        workspace = os.getenv("TOGGL_WORKSPACE_ID", "").strip()
        if not token:
            raise ValueError("TOGGL_API_TOKEN is required")
        if not workspace:
            raise ValueError("TOGGL_WORKSPACE_ID is required")
        workspace_id = int(_positive_number("TOGGL_WORKSPACE_ID", workspace, integer=True))
        poll_interval = float(_positive_number("POLL_INTERVAL", os.getenv("POLL_INTERVAL", "1")))
        toggl_sync_interval = float(
            _positive_number("TOGGL_SYNC_INTERVAL", os.getenv("TOGGL_SYNC_INTERVAL", "30"))
        )
        toggl_hourly_limit = int(
            _positive_number(
                "TOGGL_HOURLY_LIMIT", os.getenv("TOGGL_HOURLY_LIMIT", "500"), integer=True
            )
        )
        request_timeout = float(
            _positive_number("REQUEST_TIMEOUT", os.getenv("REQUEST_TIMEOUT", "10"))
        )
        return cls(
            busy_url=os.getenv("BUSY_URL", "http://10.0.4.20").rstrip("/"),
            busy_api_token=os.getenv("BUSY_API_TOKEN") or None,
            toggl_api_token=token,
            toggl_workspace_id=workspace_id,
            poll_interval=poll_interval,
            toggl_sync_interval=toggl_sync_interval,
            toggl_hourly_limit=toggl_hourly_limit,
            request_timeout=request_timeout,
        )
