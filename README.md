# busytoggl

Runs a Toggl Track timer while the BUSY Bar timer is running. Pausing or stopping
the BUSY timer stops the current Toggl timer. The bridge only reads
the BUSY Bar snapshot endpoint; it never sends display, audio, or input commands
to the bar.

## AI DISCLAIMER - THIS CODE IS BASICALLY ENTIRELY AI GENERATED
This project does not reflect the quality of my usual code. I simply generated this
with a few iterations of codex + claude reviews because I needed this as a productivity
tool, so I generated it as a quick and dirty project.

**You should review the code yourself before running it.**

I've only released it publicly because I figured it could be useful for others.

## Setup

Requires Python 3.11 or newer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
$env:TOGGL_API_TOKEN = "your token"
$env:TOGGL_WORKSPACE_ID = "your workspace ID"
busytoggl
```

Your API token is at **Toggl Track > Profile settings > API Token**. The workspace
ID is the number in a Toggl workspace URL. See `.env.example` for all settings.

If HTTP API access on the BUSY Bar uses key mode, also set `BUSY_API_TOKEN`.

## Behavior

- `INFINITE`, `SIMPLE`, or `INTERVAL` and not paused: start Toggl if stopped.
- paused or `NOT_STARTED`: stop Toggl if running.
- API errors are logged and retried without changing either timer.
- On startup, the Toggl timer is immediately synchronized to the bar state.
- Toggl is periodically reconciled, so a timer changed elsewhere is corrected.
- BUSY is polled every second, but Toggl is contacted immediately only when the
  BUSY state changes and otherwise every 30 seconds. A rolling 500-request/hour
  safety limit keeps the bridge below Toggl's free-plan quota.

When starting, the bridge copies the project, task, tags, and description from
the most recent valid Toggl entry. It appends `[Automated entry, please recheck]`
to the description and adds the `busytoggl` tag. This satisfies workspaces that
require a project, task, and description.
