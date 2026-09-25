# Browser end-to-end tests

`tools/e2e/run_all.sh` starts `ui_server.py` (the app with a fake model, stubbed prices and a fake live feed,
isolated data dir, port 8766) and runs seven Playwright suites:

- `ui_test.py`: search by Arabic name, full session to verdict, minutes expander, Stop, beginner mode,
  screens kept across navigation, report phases, model list, 390 px width, console errors.
- `new_feats.py`: virtual portfolio, reuse of today's analysis, economy pre-screen, price alert from a live
  tick, data-source switch, PDF button.
- `round3.py`: glossary modal and term popovers, trust dashboard.
- `review_fixes.py`: 2026-09 review fixes (first-run language, both markets, History currency, trust waiting) and the optional Sharia screen on/off.
- `round4.py`: index-fund option, cost-vs-amount warning, plan caps and fees, both markets in the header, verdict track record, steady pre-screen, phone-width captions.
- `persist.py`: every screen keeps its state (typed text, choices, open sections, scroll) across navigation, and a session keeps playing while you are elsewhere.
- `stop.py`: Stop is immediate right after Start, mid-run (single, watchlist, beginner) and by Esc; a shown verdict is never taken back.

`scenes_cap.py` and `live_cap.py` capture screenshots of every office scene and the live board
(`verification/e2e/`). Note: `ui_server.py` makes the fake model output say "Buy"; a test that re-runs a ticker
on the same server sees the "already analysed today" offer by design.
