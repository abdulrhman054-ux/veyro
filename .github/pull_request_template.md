## What and why
<!-- What this PR changes, and the problem it solves. Link the issue: Fixes #123 -->

## Area
- [ ] Wiring (UI ↔ backend)
- [ ] Navigation between screens
- [ ] App logic (sessions, Stop, resume, scans, spend)
- [ ] Other:

## How it was tested
- [ ] `cd backend && python -m pytest -q`
- [ ] `cd frontend && npx tsc --noEmit && npm run build`, and `frontend/dist` is committed
- [ ] `bash tools/e2e/run_all.sh` (or the suites this touches)
- [ ] A bug fix includes a test that fails before the fix
- [ ] UI checked in Arabic and English, and at 390 px

## Ground rules
- [ ] No API key reaches logs, the DB, API responses or the UI
- [ ] Execution stays off by default, and every order is confirmed
- [ ] The spend cap still blocks paid runs; same-origin and loopback checks hold
- [ ] Free data only; missing data shown as unknown, never invented
