from __future__ import annotations

import base64
import json
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ApiError(RuntimeError):
    pass


AUTOMATED_MARKER = "[Automated entry, please recheck]"


def automated_description(description: str) -> str:
    base = description.rstrip().removesuffix(AUTOMATED_MARKER).rstrip()
    return f"{base} {AUTOMATED_MARKER}".strip()


class HourlyRateLimiter:
    def __init__(self, limit: int, window: float = 3600) -> None:
        self.limit = limit
        self.window = window
        self.requests: deque[float] = deque()

    def acquire(self) -> None:
        while True:
            now = time.monotonic()
            while self.requests and now - self.requests[0] >= self.window:
                self.requests.popleft()
            if len(self.requests) < self.limit:
                self.requests.append(now)
                return
            time.sleep(max(0, self.window - (now - self.requests[0])))


def _json_request(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 10,
) -> Any:
    request_headers = {"Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
            return json.loads(payload) if payload else None
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise ApiError(f"{method} {url} returned {exc.code}: {detail}") from exc
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ApiError(f"{method} {url} failed: {exc}") from exc


class BusyClient:
    def __init__(self, base_url: str, api_token: str | None, timeout: float) -> None:
        self.url = f"{base_url}/api/busy/snapshot"
        self.headers = {"X-API-Token": api_token} if api_token else {}
        self.timeout = timeout

    def is_running(self) -> bool:
        data = _json_request(self.url, headers=self.headers, timeout=self.timeout)
        try:
            snapshot = data["snapshot"]
            snapshot_type = snapshot["type"]
            if snapshot_type == "NOT_STARTED" or snapshot.get("is_paused", False):
                return False
            if snapshot_type == "INTERVAL":
                current_interval = snapshot["current_interval"]
                if not isinstance(current_interval, int) or isinstance(current_interval, bool):
                    raise TypeError("'current_interval' must be an integer")
                return current_interval % 2 == 0
            return True
        except (KeyError, TypeError, AttributeError) as exc:
            raise ApiError(f"Unexpected BUSY snapshot structure: {exc}") from exc


class TogglClient:
    api_url = "https://api.track.toggl.com/api/v9"

    def __init__(self, api_token: str, workspace_id: int, timeout: float, hourly_limit: int = 500) -> None:
        credentials = base64.b64encode(f"{api_token}:api_token".encode()).decode()
        self.headers = {"Authorization": f"Basic {credentials}"}
        self.workspace_id = workspace_id
        self.timeout = timeout
        self.rate_limiter = HourlyRateLimiter(hourly_limit)

    def _request(self, url: str, **kwargs: Any) -> Any:
        self.rate_limiter.acquire()
        return _json_request(url, headers=self.headers, timeout=self.timeout, **kwargs)

    def current(self) -> dict[str, Any] | None:
        return self._request(
            f"{self.api_url}/me/time_entries/current",
        )

    def recent(self) -> list[dict[str, Any]]:
        # Keep the lower-bound cursor clear of the 90-day boundary despite request latency.
        since = int((datetime.now(timezone.utc) - timedelta(days=90)).timestamp()) + 15
        result = self._request(
            f"{self.api_url}/me/time_entries?since={since}",
        )
        if not isinstance(result, list):
            raise ApiError("Unexpected Toggl recent entries response")
        return result

    def start(self, template: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            f"{self.api_url}/workspaces/{self.workspace_id}/time_entries",
            method="POST",
            body={
                "created_with": "busytoggl",
                "description": automated_description(template["description"]),
                "duration": -1,
                "project_id": template["project_id"],
                "start": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "tags": list(dict.fromkeys([*(template.get("tags") or []), "busytoggl"])),
                "task_id": template["task_id"],
                "workspace_id": self.workspace_id,
            },
        )

    def update(self, entry_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            f"{self.api_url}/workspaces/{self.workspace_id}/time_entries/{entry_id}",
            method="PUT",
            body=fields,
        )

    def stop(self, entry_id: int) -> dict[str, Any]:
        return self._request(
            f"{self.api_url}/workspaces/{self.workspace_id}/time_entries/{entry_id}/stop",
            method="PATCH",
        )
