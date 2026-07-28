# AGENTS.md

## Project purpose

This is a Python 3.11+ bridge between a physical BUSY Bar and Toggl Track. The
BUSY Bar is the input/controller: its timer state starts and stops a Toggl Track
time entry.

The primary product constraint is strict:

- Read state from the BUSY Bar.
- Write timer changes only to Toggl Track.
- Never draw, display, play audio, send input, change settings, or otherwise
  write anything to the BUSY Bar.

BUSY documentation:

- Device OpenAPI schema: `http://10.0.4.20/openapi.yaml`
- User manual: `https://docs.busy.app/`
- The only runtime BUSY endpoint this application should call is the read-only
  `GET /api/busy/snapshot` endpoint.

## Repository layout

- `src/busytoggl/app.py`: synchronization policy and long-running poll loop.
- `src/busytoggl/clients.py`: BUSY and Toggl HTTP clients, response handling,
  automated-description normalization, and Toggl rate limiting.
- `src/busytoggl/config.py`: environment configuration and validation.
- `tests/test_app.py`: unit and loop-level regression tests.
- `.env.example`: supported runtime settings; `.env` contains local secrets and
  must never be committed or printed.

The project uses the `src` package layout. Run it as the installed `busytoggl`
command or as the `busytoggl.app` module. `app.py` also supports direct execution
for IDEs. PyCharm should mark `src` as a Sources Root and use the shared
`busytoggl` run configuration.

## Synchronization behavior

Interpret BUSY snapshots as follows:

- Any snapshot whose type is not `NOT_STARTED` and whose `is_paused` value is
  false: Toggl should be running.
- `NOT_STARTED` or a paused timer: Toggl should be stopped.

Do not infer a separate finished state from `time_left_ms` or interval counters
unless the BUSY API formally documents that state. The current implementation
relies on the device transitioning a completed timer to `NOT_STARTED` or paused.

On start, resume the work context from the most recent valid Toggl entry within
the search window. A valid template has an ID, non-empty description, project
ID, and task ID. Copy its project, task, tags, and description into a new entry,
add the `busytoggl` tag, and append exactly one marker:

`[Automated entry, please recheck]`

Marker formatting must be idempotent. Never append a second marker when the
template or current entry already ends with it. Toggl may return nullable fields;
in particular, treat `tags: null` as an empty tag list.

Some Toggl workspaces require project, task, and description. If an incomplete
current entry must be stopped, repair it using the most recent valid template,
then stop it. Malformed or unexpected API responses must become `ApiError`s so
the run loop logs and retries them instead of crashing.

## Polling and rate limits

BUSY is local and may be polled frequently. Toggl must not be called on every
BUSY poll.

- Synchronize Toggl immediately when BUSY running/paused state changes.
- Otherwise reconcile on `TOGGL_SYNC_INTERVAL` (default 30 seconds).
- Enforce the rolling `TOGGL_HOURLY_LIMIT` (default 500), remaining below the
  known 600-request/hour Toggl free-plan quota.
- A failed Toggl attempt consumes the current reconciliation slot; do not retry
  it every second.
- BUSY polling failures and Toggl synchronization failures should be logged and
  retried independently.

## Configuration

Supported environment variables:

- `BUSY_URL` (default `http://10.0.4.20`)
- `BUSY_API_TOKEN` (optional)
- `TOGGL_API_TOKEN` (required)
- `TOGGL_WORKSPACE_ID` (required positive integer)
- `POLL_INTERVAL` (default 1 second)
- `TOGGL_SYNC_INTERVAL` (default 30 seconds)
- `TOGGL_HOURLY_LIMIT` (default 500)
- `REQUEST_TIMEOUT` (default 10 seconds)

Validation errors must name the exact environment variable. Do not reintroduce
`TOGGL_DESCRIPTION`; descriptions come from the last valid Toggl entry.

## Development rules

- Keep runtime dependencies in the standard library unless a dependency has a
  clear benefit that justifies it.
- Use timezone-aware UTC timestamps formatted as `%Y-%m-%dT%H:%M:%SZ`.
- Preserve API errors as concise, actionable `ApiError` messages.
- Never log API tokens, authorization headers, or `.env` contents.
- Read-only calls to the live BUSY and Toggl APIs are acceptable for diagnosis.
  Do not make live mutating API calls merely to test code.
- Preserve the user's existing timer data and unrelated workspace changes.

## Verification

Run:

```powershell
python -m pytest -q
python -m compileall -q src tests
```

Add regression coverage for changes to state transitions, malformed responses,
required-field repair, marker idempotency, nullable Toggl fields, configuration
validation, retry scheduling, and hourly rate limiting. Tests must not contact
the live BUSY Bar or Toggl APIs.
