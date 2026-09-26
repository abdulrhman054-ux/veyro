# How Veyro fits together

Veyro wraps [TradingAgents](https://github.com/TauricResearch/TradingAgents) (pinned, unmodified, `v0.5.1`) in a local web app.

- **Backend.** FastAPI, SQLite and threads run the framework and speak for its agents.
- **Frontend.** React 19 plays each run as a film in a pixel-art office.
- **Desktop shell.** Electron starts the backend and shows the UI.

Everything runs on `127.0.0.1`. Nothing is served to the network.

This page is the map for anyone working on **how the app is wired**: the UI ↔ API contract, **navigation between screens** and **the app's overall logic**. The reasons behind each rule are in `DECISIONS.md`, and known gaps are in `docs/REVIEW.md`.

```
Electron (desktop/main.js) ──starts──▶ python -m veyro (backend/veyro/__main__.py, uvicorn on a free port)
        │                                         │
        └──loads http://127.0.0.1:<port>──▶ frontend/dist (React)  ◀── HTTP /api/* and WebSocket /ws/*
                                                  │
                                    backend/veyro/runner.py ──▶ TradingAgents graph (LangGraph stream)
```

## Backend (`backend/veyro/`)

| Module | What it owns |
|---|---|
| `app.py` | Every HTTP/WS route, input validation, the loopback-Host and same-origin guards, the spend-cap check before paid work |
| `runner.py` | A session's whole life: start, framework stream, voice lines, verdict, Stop, resume, scans. Also the run lock (one run per instrument, date and models), `Bus` (per-session event log and fan-out to WebSockets) and `Emitter` (keeps events in order while lines are voiced in parallel) |
| `db.py` | SQLite schema and small helpers (`sessions`, `turns`, `scans`, `paper`, settings) |
| `budget.py` | Monthly spend: recorded cost, reservations for running sessions, the side-call ledger, `blocked()` |
| `market.py`, `calendars.py` | Free market data (Yahoo via yfinance, cached) and trading calendars (XSAU / XNYS) |
| `allocation.py` | Leo's plan: caps, weights, broker fees, FX |
| `assistant.py`, `extras.py` | Track record (trust), alerts, morning report, virtual portfolio |
| `sharia.py`, `valuation.py`, `beginner.py`, `world.py`, `voice.py` | Optional Sharia screen, value pre-screen, beginner picks, world news (Albie), the in-character lines |
| `execution/` | Alpaca orders (off by default; every order needs explicit confirmation) |
| `secrets_store.py` | API keys in the OS keyring only, never in the DB, logs or responses |

### A session, end to end
1. `POST /api/sessions`: `app.create_session` checks the input and the cap (`_cap_reached`, which counts this run's own estimate), then calls `runner.start_session`.
2. `start_session` takes the **run lock**. If the same run is already playing, it returns that session (the caller attaches). If a stopped run is still winding down, it raises `StillStopping`.
3. A worker thread runs `run_session` → `_run_real` (or `_run_demo`). The framework graph streams in `_CancellableStream`. Each agent output becomes a voice job. `Emitter` publishes the events in order to the session's `Bus`.
4. The UI opens `WS /ws/sessions/{id}`. It gets the full event history, then live events. Event types (`api.ts` → `VEvent`) include:
   - `session`, `market`, `team`;
   - `agent_started`, `agent_message`, `agent_done`;
   - `verdict`, `usage`, `error`, `end`.
5. The verdict is recorded under `STATUS_LOCK`. Stop and the verdict can't both win.
6. **Stop.** `POST /api/sessions/{id}/cancel` → `cancel_session` marks the session cancelled and publishes `end` at once. The worker notices at its next step.
7. **Spend.** It is written after every model reply (`UsageTracker.persist`), so interrupted runs still count.

Scans (`start_scan`) run sessions one after another on their own `Bus` (`/ws/scans/{id}`): `scan_session`, `scan_result`, `scan_skipped`, `scan_capped`, `scan_ranked`, `end`.

## Frontend (`frontend/src/`)

| Path | What it owns |
|---|---|
| `App.tsx` | The shell: header, screen switching, keeping every visited screen mounted, scroll memory, cross-screen hand-offs |
| `api.ts` | `api.get/post/put/del` (a `{ok:false, code}` reply becomes `ApiError`), `openStream`, shared types |
| `office/Office.tsx` | The start bar (modes: I'm new / One stock / Watchlist / Market scan), the stage and the minutes. It also owns running, Stop and the scan progress |
| `office/useSession.ts` | The reducer that turns WS events into what the stage shows (the queue of lines, current line, verdict, stopping/ended) |
| `office/Room.tsx`, `scenes.ts`, `Dialog.tsx`, `fun.ts` | The stage: sets, blocking, dialogue, verdict box, easter eggs |
| `screens/*` | Live, World news, Report, History, Orders, Settings |
| `extras/*` | Trust dashboard, virtual portfolio, alerts, Sharia badges and panel, glossary |
| `prefs.tsx`, `i18n.ts` | Language (ar/en), theme, motion; every string in both languages |

### Screens and navigation (the rules)
Screens: `office | live | world | report | history | orders | settings` (`type Screen` in `App.tsx`).

- **Every screen stays mounted once visited** (`seen` set + `hidden`). Typed text, open sections and a session that's playing survive navigation. Don't unmount screens to "reset" them.
- **Scroll is remembered per screen** (`scrollOf`) and restored in a layout effect. Sending someone to the Office to *do* something uses `goOfficeTop()` (lands on the start bar).
- **Cross-screen hand-offs** go through `App.tsx`, never by one screen reaching into another:

| From | To | How |
|---|---|---|
| History "View" / verdict "Open report" | Report | `openReport(id)` (a different session's report starts at the top) |
| History "Resume" | Office | `setPendingStart({ticker, trade_date, nonce})` + `goOfficeTop()` → Office effect starts the run |
| Live "Analyse" | Office | `window` event `veyro:pick-ticker` + `goOfficeTop()` → Office fills the start bar |
| Alerts bell / morning report | Office | `setPendingScan({id, nonce})` (also the `veyro:follow-scan` event) → Office follows that scan |
| Orders "Settings" | Settings | `go("settings")` |

- While a session runs and you're on another screen, a "running" toast leads back to the Office.
- Keyboard: `/` focuses the search, Space advances a line, Esc stops a run (only on the Office, never while typing or with a dialog open).

## Rules that keep it safe (don't break these)
- API keys: OS keyring only, shown masked; never in logs, the DB, API responses or the UI.
- Alpaca execution is off by default; every order needs explicit confirmation.
- The monthly spend cap blocks paid runs, including the run about to start.
- Only loopback Host names; same-origin on HTTP and WebSocket. Dev origins only with `VEYRO_DEV=1`.
- Free data only. Missing data is "unknown", never a made-up number (and never "Sharia-compliant").
- Every bug fix comes with a test that fails before it.

## Where to start
- **Wiring (UI ↔ API):** the event types in `api.ts` and the routes in `app.py` must match. A new event needs its type, a reducer case in `useSession.ts` (or the scan reducer in `Office.tsx`) and a test.
- **Navigation:** add hand-offs in `App.tsx` only, following the table above. Cover them in `tools/e2e/persist.py`.
- **App logic:** `runner.py` (lifecycle, locks, Stop) and `budget.py` (spend) are the sensitive parts. `backend/tests/test_round4_backend.py` and `test_round5_backend.py` show how to test races with fakes.
