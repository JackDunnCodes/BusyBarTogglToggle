import pytest

from busytoggl.app import run, synchronize
from busytoggl.clients import (
    AUTOMATED_MARKER,
    ApiError,
    BusyClient,
    HourlyRateLimiter,
    TogglClient,
)
from busytoggl.config import Config


class FakeToggl:
    def __init__(self, current=None, recent=None):
        self.entry = current
        self.entries = recent or []
        self.started = 0
        self.stopped = []
        self.updated = []

    def current(self):
        return self.entry

    def recent(self):
        return self.entries

    def start(self, template):
        self.started += 1
        return {"id": 42}

    def update(self, entry_id, fields):
        self.updated.append((entry_id, fields))
        return {"id": entry_id, **fields}

    def stop(self, entry_id):
        self.stopped.append(entry_id)
        return {"id": entry_id}


def test_starts_when_busy_is_running():
    toggl = FakeToggl(recent=[valid_entry()])
    synchronize(True, toggl)
    assert toggl.started == 1


def test_stops_current_entry_when_busy_is_paused():
    toggl = FakeToggl(valid_entry(7))
    synchronize(False, toggl)
    assert toggl.stopped == [7]


def test_does_nothing_when_states_already_match():
    running = FakeToggl(valid_entry(7))
    stopped = FakeToggl()
    synchronize(True, running)
    synchronize(False, stopped)
    assert running.started == 0 and running.stopped == []
    assert stopped.started == 0 and stopped.stopped == []


def test_busy_snapshot_running(monkeypatch):
    monkeypatch.setattr(
        "busytoggl.clients._json_request",
        lambda *args, **kwargs: {"snapshot": {"type": "INFINITE", "is_paused": False}},
    )
    assert BusyClient("http://busy", None, 1).is_running()


def test_not_started_snapshot_is_stopped(monkeypatch):
    monkeypatch.setattr(
        "busytoggl.clients._json_request",
        lambda *args, **kwargs: {"snapshot": {"type": "NOT_STARTED"}},
    )
    assert not BusyClient("http://busy", None, 1).is_running()


@pytest.mark.parametrize("response", [None, {}, {"snapshot": None}, {"snapshot": {}}])
def test_malformed_busy_snapshot_raises_api_error(monkeypatch, response):
    monkeypatch.setattr("busytoggl.clients._json_request", lambda *args, **kwargs: response)
    with pytest.raises(ApiError, match="Unexpected BUSY snapshot structure"):
        BusyClient("http://busy", None, 1).is_running()


def test_current_entry_without_id_raises_api_error():
    with pytest.raises(ApiError, match="current entry missing 'id'"):
        synchronize(False, FakeToggl({"description": "missing id"}))


def valid_entry(entry_id=3):
    return {
        "id": entry_id,
        "description": "Previous work",
        "project_id": 10,
        "task_id": 20,
        "tags": [],
    }


def test_incomplete_current_entry_is_repaired_before_stop():
    toggl = FakeToggl({"id": 7, "description": ""}, recent=[valid_entry()])
    synchronize(False, toggl)
    assert toggl.updated == [
        (
            7,
            {
                "description": "Previous work [Automated entry, please recheck]",
                "project_id": 10,
                "task_id": 20,
            },
        )
    ]
    assert toggl.stopped == [7]


def test_repair_does_not_duplicate_automated_marker():
    description = f"Previous work {AUTOMATED_MARKER}"
    current = {"id": 7, "description": description, "project_id": None, "task_id": None}
    toggl = FakeToggl(current, recent=[valid_entry()])
    synchronize(False, toggl)
    assert toggl.updated[0][1]["description"] == description
    assert toggl.stopped == [7]


def test_start_does_not_duplicate_automated_marker(monkeypatch):
    captured = {}

    def capture_request(*args, **kwargs):
        captured.update(kwargs["body"])
        return {"id": 42}

    monkeypatch.setattr("busytoggl.clients._json_request", capture_request)
    template = valid_entry()
    template["description"] += f" {AUTOMATED_MARKER}"
    TogglClient("token", 1, 1).start(template)
    assert captured["description"] == f"Previous work {AUTOMATED_MARKER}"


def test_start_accepts_null_tags(monkeypatch):
    captured = {}

    def capture_request(*args, **kwargs):
        captured.update(kwargs["body"])
        return {"id": 42}

    monkeypatch.setattr("busytoggl.clients._json_request", capture_request)
    template = valid_entry()
    template["tags"] = None
    TogglClient("token", 1, 1).start(template)
    assert captured["tags"] == ["busytoggl"]


def test_run_stops_timer_for_paused_busy_snapshot(monkeypatch):
    class PausedBusy:
        def is_running(self):
            return False

    toggl = FakeToggl(valid_entry(7))
    monkeypatch.setattr(
        "busytoggl.app.time.sleep",
        lambda _interval: (_ for _ in ()).throw(KeyboardInterrupt),
    )
    with pytest.raises(KeyboardInterrupt):
        run(valid_config(), busy=PausedBusy(), toggl=toggl)
    assert toggl.stopped == [7]


def test_run_retries_api_error(monkeypatch):
    class FlakyBusy:
        calls = 0

        def is_running(self):
            self.calls += 1
            if self.calls == 1:
                raise ApiError("temporary failure")
            return False

    busy = FlakyBusy()
    sleeps = 0

    def stop_after_retry(_interval):
        nonlocal sleeps
        sleeps += 1
        if sleeps == 2:
            raise KeyboardInterrupt

    monkeypatch.setattr("busytoggl.app.time.sleep", stop_after_retry)
    with pytest.raises(KeyboardInterrupt):
        run(valid_config(), busy=busy, toggl=FakeToggl())
    assert busy.calls == 2


def valid_config() -> Config:
    return Config("http://busy", None, "token", 1, 0.01, 30, 500, 1)


def test_hourly_rate_limiter_waits_at_limit(monkeypatch):
    clock = [0.0]
    sleeps = []

    monkeypatch.setattr("busytoggl.clients.time.monotonic", lambda: clock[0])

    def advance(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr("busytoggl.clients.time.sleep", advance)
    limiter = HourlyRateLimiter(limit=2, window=10)
    limiter.acquire()
    limiter.acquire()
    limiter.acquire()
    assert sleeps == [10]


def test_config_requires_token(monkeypatch):
    monkeypatch.delenv("TOGGL_API_TOKEN", raising=False)
    monkeypatch.setenv("TOGGL_WORKSPACE_ID", "1")
    with pytest.raises(ValueError, match="TOGGL_API_TOKEN is required"):
        Config.from_env()


def test_config_requires_workspace(monkeypatch):
    monkeypatch.setenv("TOGGL_API_TOKEN", "token")
    monkeypatch.delenv("TOGGL_WORKSPACE_ID", raising=False)
    with pytest.raises(ValueError, match="TOGGL_WORKSPACE_ID is required"):
        Config.from_env()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TOGGL_WORKSPACE_ID", "abc"),
        ("POLL_INTERVAL", "abc"),
        ("TOGGL_SYNC_INTERVAL", "abc"),
        ("TOGGL_HOURLY_LIMIT", "abc"),
        ("REQUEST_TIMEOUT", "abc"),
    ],
)
def test_config_rejects_non_numeric_values(monkeypatch, name, value):
    monkeypatch.setenv("TOGGL_API_TOKEN", "token")
    monkeypatch.setenv("TOGGL_WORKSPACE_ID", "1")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match="must be numeric"):
        Config.from_env()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TOGGL_WORKSPACE_ID", "0"),
        ("POLL_INTERVAL", "0"),
        ("TOGGL_SYNC_INTERVAL", "0"),
        ("TOGGL_HOURLY_LIMIT", "0"),
        ("REQUEST_TIMEOUT", "-1"),
    ],
)
def test_config_rejects_non_positive_values(monkeypatch, name, value):
    monkeypatch.setenv("TOGGL_API_TOKEN", "token")
    monkeypatch.setenv("TOGGL_WORKSPACE_ID", "1")
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match="must be positive"):
        Config.from_env()
