# Contributing to Veyro

Thanks for helping. Veyro is a bilingual (Arabic / English) desktop app built on [TradingAgents](https://github.com/TauricResearch/TradingAgents).

> **بالعربي باختصار:** نرحب بالمساهمات، وأكثر شي نحتاجه ثلاثة مجالات:
> 1. **الربط العام للتطبيق:** توافق الواجهة مع الخلفية وأحداث الجلسة.
> 2. **التنقل المنطقي بين الشاشات:** كل شاشة تحفظ حالتها، والانتقالات واضحة ومتوقعة.
> 3. **منطق التطبيق العام:** دورة الجلسة، الإيقاف، الاستئناف، المسح، وسقف الصرف.
>
> - افتح Issue قبل أي تغيير كبير.
> - كل إصلاح لازم معه اختبار يفشل قبله وينجح بعده.
> - لا تكسر قواعد الأمان تحت.
> - تقدر تكتب الـ Issue أو الـ PR بالعربي أو الإنجليزي.

## What we need most

Before starting, read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). It maps the modules, the session lifecycle and the navigation rules.

1. **App-wide wiring (UI ↔ API)**
   - The WebSocket event types in `frontend/src/api.ts` should match what `backend/veyro/runner.py` publishes. Each event needs a reducer case and a test.
   - Error codes (`{ok:false, code}`) should always reach a clear message in both languages. None may be swallowed silently.
   - The session, scan, report and plan data should be consistent everywhere they're shown (History, Report, Trust, virtual portfolio).
2. **Logical navigation between screens**
   - Every screen keeps its state and scroll position.
   - Hand-offs (Resume, Analyse, Open report, following a scan) go through `App.tsx` only.
   - Back and forward feel predictable, and no action leaves you on a screen with nothing to do.
   - Keyboard and screen-reader paths work too.
   - Cover changes in `tools/e2e/persist.py` or a new e2e check.
3. **Overall app logic**
   - Session lifecycle: start, attach, Stop, resume, scan skip and cancel.
   - Spend cap and reservations.
   - Race conditions between Stop, the verdict and late model replies.
   - Clear states for "unknown", "waiting" and "unavailable" instead of guesses.

Issues labelled **`good first issue`** are small and self-contained. **`help wanted`** marks bigger items.

## Ground rules (a PR that breaks one of these won't be merged)

- **API keys** live only in the OS keyring and are shown masked. They never appear in logs, the database, API responses or the UI.
- **Order execution** (Alpaca) is off by default, and every order needs explicit confirmation. Changes to `backend/veyro/execution/` need the maintainer's review (see `.github/CODEOWNERS`).
- **The monthly spend cap** blocks paid runs, including the run about to start.
- **Same-origin and loopback-Host checks** hold on HTTP and WebSocket.
- **Free data only**: no paid subscriptions.
- Missing data is shown as unknown and never invented. The Sharia screen never treats missing data as compliant.
- **Every bug fix comes with a test** that fails before the fix and passes after. Keep fixes minimal.
- Veyro is **not financial advice**. Don't add wording that promises returns or reads as a recommendation.
- TradingAgents stays a pinned, unmodified dependency. Fix things in Veyro, or upstream at TradingAgents.

## Set up

Requirements: Python 3.11+, Node 20+ (only for frontend work), and Git.

```bash
git clone https://github.com/abdulrhman054-ux/veyro.git
cd veyro
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt pytest httpx
cd backend && python -m veyro          # serves http://127.0.0.1:8765 using the built frontend/dist
```

On Windows you can also double-click `start.bat`.

For frontend work, run `cd frontend && npm ci && npm run dev`. It proxies `/api` to 8765. Start the backend with `VEYRO_DEV=1` if you need the Orders screen from the dev server.

**Demo mode** needs no API key and costs nothing. Use it to click through the app.

## Test

```bash
cd backend && python -m pytest -q                  # backend unit tests (no network, no keys)
cd frontend && npx tsc --noEmit && npm run build   # types + build
bash tools/e2e/run_all.sh                          # browser suites against a stub server (fake model, stub prices)
```

- For the browser suites: `pip install playwright`, then `python -m playwright install chromium`.
- You can run one suite with `SUITES=persist bash tools/e2e/run_all.sh`. Details are in `tools/e2e/README.md`.
- **Rebuild `frontend/dist` after any frontend change and commit it.** The app ships the built UI so users don't need Node. CI checks that `frontend/dist` matches the source.

## Pull requests

1. Open or pick an issue first for anything bigger than a small fix.
2. Branch from `main`, and keep each PR to one topic.
3. Write the "why" in the PR description. Record decisions that change behaviour in `DECISIONS.md` (the next number).
4. Test both languages (Arabic RTL and English) and a narrow screen (390 px) when you touch the UI.
5. CI must be green. A maintainer reviews every PR before it's merged.

Commit messages: an imperative summary line, then the reason.

## Reporting bugs and security issues

- Bugs and ideas: use the issue templates.
- **Security problems** (key exposure, a way past the spend cap or the same-origin checks, unconfirmed orders): **don't open a public issue**. See [`SECURITY.md`](SECURITY.md).

By contributing, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE) and that you follow the [Code of Conduct](CODE_OF_CONDUCT.md).
