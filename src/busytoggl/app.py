from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Protocol

if __package__:
    from .clients import ApiError, BusyClient, TogglClient, automated_description
    from .config import Config
else:
    # Support IDEs configured to execute this file instead of the package module.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from busytoggl.clients import ApiError, BusyClient, TogglClient, automated_description
    from busytoggl.config import Config

LOG = logging.getLogger("busytoggl")


class BusyState(Protocol):
    def is_running(self) -> bool: ...


class Timer(Protocol):
    def current(self) -> dict | None: ...
    def recent(self) -> list[dict]: ...
    def start(self, template: dict) -> dict: ...
    def update(self, entry_id: int, fields: dict) -> dict: ...
    def stop(self, entry_id: int) -> dict: ...


def _is_valid_entry(entry: object) -> bool:
    description = entry.get("description") if isinstance(entry, dict) else None
    return (
        isinstance(entry, dict)
        and entry.get("id") is not None
        and isinstance(description, str)
        and bool(description.strip())
        and entry.get("project_id") is not None
        and entry.get("task_id") is not None
    )


def _last_valid_entry(toggl: Timer) -> dict:
    try:
        return next(entry for entry in toggl.recent() if _is_valid_entry(entry))
    except StopIteration as exc:
        raise ApiError(
            "No recent Toggl entry has a description, project, and task; "
            "create one in Toggl before using BUSY Bar"
        ) from exc


def synchronize(running: bool, toggl: Timer) -> None:
    current = toggl.current()
    if running and current is None:
        entry = toggl.start(_last_valid_entry(toggl))
        if not isinstance(entry, dict) or entry.get("id") is None:
            raise ApiError("Toggl start response missing 'id'")
        LOG.info("Started Toggl entry %s", entry["id"])
    elif not running and current is not None:
        if not isinstance(current, dict) or current.get("id") is None:
            raise ApiError("Toggl current entry missing 'id'")
        entry_id = current["id"]
        if not _is_valid_entry(current):
            template = _last_valid_entry(toggl)
            raw_description = current.get("description")
            description = raw_description.strip() if isinstance(raw_description, str) else ""
            if not description:
                description = template["description"].strip()
            toggl.update(
                entry_id,
                {
                    "description": automated_description(description),
                    "project_id": template["project_id"],
                    "task_id": template["task_id"],
                },
            )
            LOG.info("Repaired incomplete Toggl entry %s before stopping", entry_id)
        toggl.stop(entry_id)
        LOG.info("Stopped Toggl entry %s", entry_id)


def run(config: Config, busy: BusyState | None = None, toggl: Timer | None = None) -> None:
    busy = busy or BusyClient(config.busy_url, config.busy_api_token, config.request_timeout)
    toggl = toggl or TogglClient(
        config.toggl_api_token,
        config.toggl_workspace_id,
        config.request_timeout,
        config.toggl_hourly_limit,
    )
    previous_running: bool | None = None
    last_sync = float("-inf")
    while True:
        try:
            running = busy.is_running()
        except ApiError as exc:
            LOG.warning("BUSY polling failed; retrying: %s", exc)
        else:
            now = time.monotonic()
            should_sync = (
                running != previous_running or now - last_sync >= config.toggl_sync_interval
            )
            if should_sync:
                # Record the attempt even when Toggl rejects it, preventing rapid
                # retries from exhausting an already constrained API quota.
                previous_running = running
                last_sync = now
                try:
                    synchronize(running, toggl)
                except ApiError as exc:
                    LOG.warning("Toggl synchronization failed; retrying later: %s", exc)
        time.sleep(config.poll_interval)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = Config.from_env()
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    try:
        run(config)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
