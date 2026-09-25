# Veyro: Final Report

## What was built
A local web app (FastAPI + React/TypeScript, prebuilt; started with a double-click on `start.bat`) where **9 original pixel-art animal colleagues** run **TradingAgents v0.5.1** (Apache-2.0, pinned, unmodified) live and deliver a recommendation.

- **Office:** 8 desks. Each character animates with its real framework node: types while thinking, stands up and talks while its line plays, puts a sticky note up when done. Each has its own synthesized voice and speaking style. Leo announces the verdict with confetti. There are three ways to run: one stock (optionally for a **past date**, analysed point-in-time), a watchlist of up to 5, or a market scan from real Yahoo screeners, which Leo ranks at the end.
- **Market mood:** the whole room follows the real latest close: faces (by personality), weather, plants, the whiteboard chart with ▲/▼ and %, and a New York market clock that turns green when open and red when closed.
- **Albie the albatross (World news page):** real headlines from major Arabic and English publishers, live world market tiles (including TASI), an open-web news search with strong sources first and analysis, and "link world news to a stock". In every session he flies into the office before Leo's verdict to link the day's world news to the stock's real move.
- **Report:** Leo's verdict, conviction and price at verdict; the framework's key figures (entry, stop-loss, price target, sentiment score); session setup (team, rounds, date, benchmark, portfolio used, framework memory lessons); data sources and notices; per-character cards with the full analysis; and **the framework's full report as a ZIP**.
- **History:** an honest scoreboard against each market's own benchmark; acted-on vs ignored calls; **the framework's own settled decision memory** (return and alpha); **the framework's backtest** (hit rate and mean alpha per rating); **Resume** for interrupted sessions (framework checkpoints).
- **Orders (optional Alpaca execution, Off by default):** Paper, Mock or Live, a two-step confirmed ticket, backend-enforced risk limits, kill switch, portfolio and a localised audit log with CSV export. See EXECUTION_REPORT.md.
- **Settings:** provider (Claude, OpenAI, DeepSeek; plus Gemini, Grok and local Ollama under Advanced), masked key in Windows Credential Manager, models, language, day/night/system theme, animation intensity, reduced motion, voices and cost display. The analyst team, debate and risk rounds, reasoning depth and optional data keys (FRED, Alpha Vantage, Jev) sit under Advanced. About screen with a TradingAgents credit.
- **Language:** the Arabic screen is 100% Arabic (RTL) and the English screen 100% English. Switching mid-session re-voices lines in character. **Ease of use:** Leo's 3-step first-visit guide; Demo mode needs no key.

## Verified, and how
- **Browser, end to end:** `tools/verify_app.py` (Playwright, Chromium) → **57/57 checks passed** (`verification/results.json`). Screenshots are in `verification/` and `verification/execution/`. It runs against a test server (`backend/tests/verify_server.py`) with an isolated database, a fake model whose output is labelled [TEST]/[اختبار], and a planted fake key. Covered:
  - every character spoke in sync with its framework node, in order, including Albie before the verdict (`02`, `03`);
  - verdict with disclaimer and price; Report with key figures and ZIP export (`04`);
  - English screen with zero Arabic (`05`, `14`); RTL on in Arabic, off in English;
  - History saved, plus framework memory and backtest (`06`, `15`); night theme (`07`); masked key (`08`);
  - scan ranking (`09`); 390 px phone width with no horizontal scroll (`10`); reduced motion (`11`);
  - team selection and crypto (Benny and Buzz on a break) (`12`, `13`); World news with real publishers and TASI (`14`);
  - **the API key never appears** in HTTP responses, WebSocket frames or server logs; **zero browser console errors**;
  - all execution checks (`e01`–`e13`).
- **Unit tests:** `backend/tests/test_execution.py`, 18 passing.
- **Pipeline scripts:**
  - `run_fake_session.py`: the real TradingAgents graph with real Yahoo data, stock and crypto, past date priced at that day's real close (AAPL 2026-09-01 → $325.13);
  - `run_resume_check.py`: stopped mid-run, then resumed from the framework checkpoint with all characters replayed;
  - `run_backtest_check.py`: framework backtest, 2 cells settled against real prices, hit rate 50%, mean alpha +1.2% with the test model.
- **`start.bat` from a clean copy** (no `.venv`): installed everything in about 2 minutes, served the app, and the health check passed.
- **Walking bug measured:** the walker stays a constant 72×78 px (it had been inheriting the whiteboard's size through a class-name clash).

## Design changes
See DESIGN_CHANGES.md (23 entries): redrawn sprites (Tank's shell and helmet, Pip's beak, Bolt's horns), happy/worried expressions, layout overlaps fixed, the whiteboard and clock wired to real data, night mode, Albie, walking, the consistent page header with a host per screen, and advanced settings folded away. Design canvas: https://claude.ai/artifact/UEdaF56Hd31MFqbFFbbySu

## Key decisions
See DECISIONS.md (57 entries). The main ones:
- TradingAgents is streamed through its public graph API.
- Risk debaters are merged into Tank's voice, and three nodes into Leo's.
- Owner-directed pure-language UI, including Arabic names and catchphrases.
- Arabic detail translated on demand.
- The same yfinance vendor as the framework, with "unavailable" rather than invented numbers.
- Conviction is read from the decision text and shown as "not stated" when absent.
- Execution Off by default, with a two-step token and limits re-checked at confirm.

## Known limitations
- **No real LLM key was available, so no session ran against Claude/OpenAI/DeepSeek.** Every live path was exercised with a fake model; voice quality, Arabic tone, conviction extraction and real cost figures still need a real key.
- Only Anthropic prices are verified; other providers show token counts.
- News relies on public RSS and the Google News index, and a publisher can change or close its feed (the UI marks a feed unavailable).
- Mock broker fills are simulated (labelled MOCK). Alpaca Paper and Live were never called (no keys).
- Backtest is capped at 3 tickers × 12 dates. Results are indicative (one model sample per cell; news feeds aren't archived).
- The market-closed flow was verified only while the US market was actually closed.

## Not tested
- A full session with a real provider key (any provider), including Ollama running locally.
- Real Alpaca Paper orders, and Live (deliberately never).
- The FRED, Alpha Vantage and Jev optional keys.
- The owner's other browsers (verified in Chromium) and screen readers beyond the accessibility tree.

## Risks
- Real-money execution, if enabled, can lose money. It's recommendation-first, with limits and confirmations, but the user is responsible.
- LLM outputs can be wrong. The voice layer is instructed to preserve substance, but paraphrase risk remains, so the full English original is always one click away.
- Model IDs and prices change over time. The model lists come from the framework's catalog, and the Anthropic prices are in `config.PRICING`.

## Owner decisions (answered)
1. First live run: **Claude** (answered).
2. Quick model: **Sonnet 5** (answered).
3. Albie's open-web search: **on** (answered).
