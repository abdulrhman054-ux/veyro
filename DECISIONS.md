# Veyro: Decisions Log

Each entry: **what** was decided, **why**, and the **alternatives** considered.

## Framework & licensing
1. **TradingAgents v0.5.1, pinned as a pip dependency from its git tag. Not forked.** Why: the brief requires wrapping, not editing. Veyro drives it only through public pieces: `TradingAgentsGraph`, `create_run_state`, `propagator.get_graph_args`, `graph.stream`, `process_signal` and `record_decision`. Alternative: a git submodule, rejected because a pip pin is simpler to install with `start.bat`.
2. **License verified: Apache-2.0** (GitHub, plus the package's `dist-info/licenses/LICENSE`). A copy is in `third_party/TradingAgents/LICENSE`, and the About screen credits it. There is no NOTICE file in the v0.5.1 source tree. The product is named **Veyro**, never "TradingAgents".
3. **Live streaming uses LangGraph `stream_mode=["updates","tasks"]`.** Why: `tasks` gives true node-start events (a character starts "thinking") and `updates` gives each node's output (the character speaks). No framework callbacks or edits were needed.

## Agent → character mapping (Decision Rule: map by function, merge, never drop)
| Framework node | Character | UI treatment |
|---|---|---|
| Market Analyst (+ its tool node) | Ollie | own line |
| Sentiment Analyst | Buzz | own line |
| News Analyst (+ tools) | Pip | own line |
| Fundamentals Analyst (+ tools) | Benny | own line |
| Bull Researcher | Bolt | a line per debate round |
| Bear Researcher | Bruno | a line per debate round |
| Research Manager, Trader | Leo | one line each |
| Aggressive / Conservative / Neutral risk analysts | Tank | **merged into one voice** after the risk round; all three full texts are kept in the report |
| Portfolio Manager | Leo | the verdict |

- The framework's analyst order is market, social, news, fundamentals, so the office seats run right-to-left in that order: Ollie, Buzz, Pip, Benny.

## Language
4. **(User direction, supersedes the brief's "names/catchphrases English".)** The English screen is fully English and the Arabic screen fully Arabic, including character names (أولي، بيب…), catchphrases (هوو هوو!، سكوااك!…), the verdict, errors and Report details. Switching language mid-session re-voices lines in the new language, in character, on demand (`/api/turns/{id}/translate`, `/api/sessions/{id}/verdict_text`) and caches them. Why: the owner explicitly asked. Alternative: locking the language during a session, rejected as less friendly.
5. The framework reasons in English (`output_language: English`). A separate voice call per agent turns its conclusion into 1–3 in-character sentences with strict rules: same substance, no new facts or numbers, never soften risks.
6. Each character has a **written speaking style per language** (`config.STYLE`) and a **distinct synthesized voice** (waveform, register, glide, vibrato or harmony, typing pace) in `audio.ts`.
7. Arabic detail translations are made **on demand** when a Report card is opened, then cached. Why: this avoids about 12 extra LLM calls per session that are often never read. The English original always stays available.

## Data honesty
8. Prices, charts, the SPY comparison, screeners and market status come from **yfinance**, the framework's own default vendor. Anything missing shows "unavailable"/"غير متوفر". Nothing is estimated.
9. **Conviction** isn't a framework output. Leo's voice call reads the decision text and returns low/medium/high, or **"not stated"** when the text doesn't make it clear. It is labelled "conviction" (قوة القناعة), not presented as a statistic.
10. **Demo mode** is scripted and clearly labelled: "[Demo]/[تجريبي]" on every line, a DEMO badge on the whiteboard, rating "DEMO". It contains no market claims. The whiteboard chart in Demo still uses real Yahoo prices.
11. **Market mood** (user direction): the office reacts to the real latest-vs-previous close of the stock under discussion, or of SPY between sessions. Thresholds: ±0.3% is up/down, ±2% is rally/slump. That drives faces (happy/worried, per personality), sweat and sparkles, weather, drooping plants, the whiteboard arrow and %, and a New York market clock with an open/closed ring. With no data, the mood is neutral.

## Market scan & watchlists (user direction)
12. Three ways to run: **one stock**, a **watchlist** of up to 5, or a **market scan** using yfinance predefined screeners (most active, gainers, losers, undervalued large caps and growth, growth tech). Scans are capped at 5 candidates and run each one as a full sequential session, then Leo ranks them by rating: Buy, Overweight, Hold, Underweight, Sell. Candidates are shown with their real price and % before starting, and the cost estimate multiplies by N.

## Architecture
13. **FastAPI + WebSocket** with an in-memory event bus per session. The backlog is replayed to late subscribers, so reloading or switching screens never loses events. The Office component stays mounted while you visit other screens, so a session keeps playing.
14. **Voice lines are generated in a small thread pool while the graph continues.** An ordered emitter keeps events in sequence. Why: parallel voice calls cut roughly 30 seconds of dead time per session.
15. **The frontend is prebuilt (`frontend/dist`) and shipped.** `start.bat` needs Python only, not Node. Why: the owner is non-technical.
16. **Keys:** OS keyring (Windows Credential Manager) → `.env` for development only → none. The API only ever returns masked keys (`sk-…abcd`). A logging filter scrubs key patterns and every key value seen by the process.
17. **Models (Anthropic IDs verified in the Claude API reference and the framework's catalog):** quick = `claude-sonnet-5` (default) or `claude-haiku-4-5`; deep = `claude-opus-5-5`. Prices (per 1M tokens, in/out): Haiku 4.5 $1/$5, Sonnet 5 $2/$10, Opus 5.5 $4/$20. OpenAI and DeepSeek prices aren't verified, so the UI shows token counts and "price unknown" rather than guessing. The pre-session estimate uses a token envelope, shown as a range.
18. **Pixel art:** all 8 sprites were redrawn as original 24×26 data (`frontend/src/art/sprites.json`), shared by the design canvas generator (`tools/sprites.py`) and the React renderer. See DESIGN_CHANGES.md.

## Optional execution (Alpaca add-on, confirmed by the owner: «نعم… اجعلها اختيارية»)
19. **Off by default.** The modes are Off / Paper / Live. Live needs: validated live keys (keyring only, never `.env`), confirmed Live risk limits, and the typed phrase «أفهم أن هذا مال حقيقي» (or its English equivalent on the English screen). Leaving Live **re-locks** it (safety over convenience). A LIVE badge shows in the header while Live is on.
20. **Paper without keys → "Mock" broker**, an in-app simulation labelled MOCK everywhere. It uses real Yahoo prices and simulated fills, cash and positions, and never contacts Alpaca. Why: the brief allows mocked responses when paper keys are missing, and it lets the owner practise. Alternative: blocking Paper entirely, rejected as less useful.
21. **Two-step tickets.** `propose` returns a one-time token (5-minute expiry). `confirm` needs `{token, confirm:true}` and **re-runs every limit**. `submit` is called from exactly one function (`service.confirm`), and a unit test checks this with an AST scan.
22. **Conservative default limits:** $500 per order, $1,000 exposure per stock, $200 daily loss, 5 orders a day. All are editable, bounded, and enforced on the server.
23. **Cash only:** a buy's cost must be ≤ min(cash, non-marginable buying power). **No shorting:** sells are limited to shares held. Only `us_equity` tradable assets, market or limit, DAY time-in-force, no extended hours. Limit orders use whole shares; market buys may be in dollars (notional) when the asset is fractionable.
24. **Closed market:** a market order is refused with Leo's offer to switch to a limit order that waits for the next open, or cancel. Nothing is queued silently.
25. **Kill switch** cancels all open orders and sets mode Off. **Liquidation** is separate and needs a typed phrase.
26. **The execution API is same-origin only:** mutating routes require the Veyro page's Origin, blocking other local pages or scripts.
27. `VEYRO_BLOCK_LIVE=1` (tests and verification) makes a live broker impossible to construct. `VEYRO_MOCK_CLOCK_OPEN=1` makes the **Mock** broker act as if the market were open, for night-time testing. It never affects Alpaca and is shown as "Mock clock (dev)".

## Fixes to the brief
- "Framework agent roles differ": the framework has 12 agent nodes for 8 characters, mapped as in the table above.
- The brief's Anthropic default "Haiku 4.5 or Sonnet 5 for quick": Sonnet 5 is the default because it's the framework catalog's first quick choice. Haiku 4.5 is selectable.
- DeepSeek: `deepseek-chat`/`deepseek-reasoner` are deprecated in the framework's catalog, so `deepseek-flash` / `deepseek-v4-pro` are used.

## TradingAgents feature coverage (owner: "make every screen fit TradingAgents' capabilities")
28. **Team selection:** choose which of the framework's 4 analysts attend (`selected_analysts`). Absent characters sit at their desk "on a coffee break" (greyed, zzz). Progress counts only those attending.
29. **Debate depth:** `max_debate_rounds` and `max_risk_discuss_rounds` (1–3) come from Settings. Bolt/Bruno speak once per round; Tank still speaks once, merging the risk round(s).
30. **Crypto:** the framework's own `normalize_symbol`/`crypto_base` detect crypto (e.g. BTC-USD). As in the framework CLI, fundamentals are dropped, so Benny takes a break automatically. Trading remains US-equities-only.
31. **Portfolio context:** when optional execution is on, the broker's cash and positions are passed as the framework's `PortfolioContext`, so the Portfolio Manager decides knowing the book. The Report shows exactly what the framework saw.
32. **Framework memory:** the framework's reflection memory (`past_context`: earlier same-ticker decisions and lessons) is stored per session and shown in the Report.
33. **Structured outputs surfaced:** the Research Manager's recommendation; the Trader's action, entry price, stop-loss and sizing; the Portfolio Manager's price target and time horizon; the Sentiment Analyst's band, score and confidence. They're parsed from the framework's own rendered markdown and labelled as the agents' estimates, not market prices. The Trader's entry price pre-fills the limit price on the order ticket.
34. **Benchmarks:** History compares each call with the framework's `benchmark_map` index (SPY for US, ^N225 for .T, …) instead of always SPY.
35. **Optional data vendors:** FRED and Alpha Vantage keys can be added (keyring). The Report notes when they're off; Yahoo Finance stays the free default.

## Albie the albatross: world news courier (owner request)
36. A 9th character on his **own page** ("World news" / «أخبار العالم»): an aviator-cap albatross, chatty in both languages.
37. **Sources:** major publishers' public RSS. English: Bloomberg (markets, economics), Reuters, FT, WSJ, CNBC, The Economist, BBC Business, MarketWatch. Arabic: Argaam, Asharq Bloomberg, Al Arabiya Aswaq, Al-Eqtisadiah, Reuters Arabic, Al Jazeera Economy. Some come via the Google News index where the publisher has no public RSS. Each language's screen shows that language's publishers. Only headline, link, time and the feed's short description are shown, always linked to the original.
38. **"Any strong source on the internet" (owner request):** a free-text search over the open web's news (Google News index, last 7 days). Results from a list of strong publishers and official bodies (Reuters, Bloomberg, FT, WSJ, AP, IMF, the Fed, OPEC, SAMA, Saudi Exchange, Argaam, …) rank first and are marked. Albie then analyses the topic in 4 parts (what is happening / why it may matter / assets to watch / what next), naming a publication for every claim, using hedged language and adding no new facts.
39. **Linked to the other agents (owner request):** in every real session, right before the Portfolio Manager's verdict, Albie flies into the office. He links the day's headlines to the stock's **real** last move plus excerpts of the framework's news and market reports, and his segment is saved as a Report turn. It's a Veyro layer on top of the framework, which stays unmodified.
40. **Market tiles:** S&P 500, Nasdaq, Dow, TASI, FTSE, DAX, Nikkei, Hang Seng, Brent, gold, the dollar index, the US 10-year yield and Bitcoin, from Yahoo. TASI keeps only one day of history on Yahoo, so its change uses the live quote (last price vs previous close).

## Walking characters (owner request)
41. Characters stroll their "job" on each screen with new walking frames (alternating legs): Leo reviews on the Report, Tank audits on History, Tank patrols and Pip watches fills on Orders (Tank walks faster in Live), Benny tidies Settings, Pip runs news and Albie glides across the sky on World news. They're decorative (`aria-hidden`), slow down on "Calm", and stand still with reduced motion.

## Console hygiene
42. Expected business-rule refusals (risk limits, closed market, locked Live, no key) return HTTP 200 `{ok:false, code}` instead of 4xx, so the browser console only shows real faults. Malformed requests still get 4xx.

## Full TradingAgents coverage, second pass (owner: "make sure every screen covers its features")
43. **Point-in-time analysis date** ("Past date?" in the start bar). The framework only feeds agents data up to that day, and the verdict is priced at that day's real close.
44. **Checkpoint resume:** `checkpoint_enabled` is always on. A stopped or crashed session shows **Resume** in History; the framework continues from its last finished node, and Veyro replays the finished characters' lines so the story stays whole.
45. **Framework decision memory** (History): the framework's own log of every decision, settled after its holding period with realised return and alpha against the regional benchmark, plus the reflection it learns from.
46. **Framework backtest** (History): `tradingagents.backtest.run_backtest` + `summarize`. Up to 3 tickers × 12 dates, estimated cost shown and a confirmation required before running; hit rate and mean alpha per rating.
47. **Report export:** `save_reports` → the framework's own markdown report tree, downloadable as a ZIP.
48. **Providers:** model lists are read from the framework's `MODEL_OPTIONS` catalog. Advanced settings add Google Gemini, xAI Grok and **Ollama (local, free, no key)**.
49. **Reasoning depth** (Auto/Light/Medium/Deep) maps to the framework's `anthropic_effort` / `openai_reasoning_effort` / `google_thinking_level`.
50. **Jev social screening:** an optional TypeSafe key, used by the framework's sentiment analyst.
51. Deliberately **not** exposed: `output_language` (the brief keeps agent reasoning in English, and the voice layer localises) and custom model IDs (too error-prone for a non-technical owner).

## Consistency pass (owner: "every screen consistent and harmonious, and the team too")
52. **One page header on every screen:** a title, one friendly line, and the screen's host strolling in a lane. Each host's job matches the screen: Benny writes the Report minutes, Bruno the skeptic keeps the honest scoreboard (History), Tank guards Orders with Pip announcing fills, Ollie explains Settings, and Albie flies over World news. No character appears twice on a screen.
53. **Roles disambiguated:** Pip is "Stock News Analyst" (company and sector news); Albie is "World News Courier" (global markets and economy).
54. **Session progress dots** include Albie, in speaking order: Ollie, Buzz, Pip, Benny, Bolt, Bruno, Tank, Albie, Leo.
55. **The audit log is fully localised** (event names, modes and details); the backend keeps stable English codes, and the CSV stays in English for tools.
56. The Orders screen when execution is off shows a friendly explainer from Tank with a button to Settings.
57. History wording says "benchmark" instead of "SPY", because the comparison follows the framework's benchmark map.

## Owner decisions (2026-09-25)
58. First real provider: **Claude**. Default quick model: **Claude Sonnet 5**, deep model Claude Opus 5.5 (both already the defaults).
59. Albie's open-web news search stays **on** by default.

## Daily assistant, API fixes and the desktop app (owner request, 2026-09-25)
60. **Favourites** (★) drive a quotes strip in the Office (real Yahoo quotes), smart alerts and the morning report.
61. **Smart alerts** (on by default, free): Pip fires when a favourite moves ≥ the threshold (3% default; it re-alerts only when the move grows by another step), and Albie when a strong publisher's fresh headline (under 3 h old) names the stock. There's a header bell, and Windows notifications come through the Notification API (Electron lets them through).
62. **Morning report** (opt-in, because every stock is a paid session): on trading days at the chosen local time, the team runs a watchlist scan of up to 5 favourites. Leo posts an alert, and "See results" follows the scan in the Office. "Run it now" is also available.
63. **Ask the team:** one grounded call picks the owning character and answers only from the session's notes (JSON: character plus answer), in the screen's language. Asked in the Office, the character stands up and answers in the dialogue box. Q&A is stored per session.
64. **Bruno's monthly card:** deterministic numbers only (direction hit rate by rating and by ticker, plus the framework's settled mean alpha); no LLM involved.
65. **API root cause found with the owner's real key:** the Anthropic key is an organisation key that isn't scoped to a workspace, so the API demands an `anthropic-workspace-id` header. Fix without touching the framework: a local relay (`/anthropic-relay`, loopback only) is set as the framework's documented `backend_url` and the voice layer's `base_url`, and it adds the header. The owner pastes the Workspace ID (`wrkspc_…`) in Settings; "Test connection" makes one tiny real call per chosen model and explains any failure in plain words. The owner's key can't list workspaces (permission error), so the ID must be pasted.
66. **One path for keys:** every LLM feature (sessions, translation, the verdict, Albie's briefing, analysis and link, ask, backtest, the morning report) activates the key through `runner.activate_key` and resolves the relay the same way. Keyless Ollama no longer crashes those paths.
67. **Any model ID:** besides the framework's catalog, "✎ Another model" accepts any ID matching `[A-Za-z0-9][A-Za-z0-9._:/@-]{1,99}`. It's tested immediately with "Test connection".
68. **Desktop:** Electron 38 portable. `Veyro-Portable.exe` (single file, about 130 MB) and a `win-unpacked` folder. It bundles a copy of CPython 3.13 plus the backend packages (about 207 MB; dev tools like Playwright and pytest are excluded). It picks a free port from 8765, keeps data in `Veyro-Data` beside the app, runs one instance at a time, keeps working from the tray when closed, opens external links in the normal browser, and uses a context-isolated renderer with no Node access.

## Second development round (owner requests, 2026-09-25)
69. **Any model, any provider.** All current Claude models are offered for both roles with list prices (longest-prefix pricing, so `claude-opus-5-5` is never priced as `claude-opus-5`). "Load every model I can use" lists the account's models live (Anthropic Models API, OpenAI-compatible `/models`, Ollama tags). Added the framework's other providers: Mistral, Qwen, GLM, Kimi, MiniMax, OpenRouter, Groq. Each provider shows a **recommended pair** with the reason; for Claude: Sonnet 5 quick + Opus 5.5 deep (Haiku 4.5 cheapest, Fable 5.1 top quality at a much higher price).
70. **Find stocks by name.** Yahoo's search plus a local Arabic/Saudi alias list (Yahoo doesn't understand Arabic names). Symbols follow the backend rule, so `2222.SR` and `BTC-USD` are accepted.
71. **Batch sizes:** watchlists up to 50, scans up to 25, morning report count configurable. Each stock is a full paid session, so above 5 the UI confirms with the multiplied estimate.
72. **Budget.** Optional amount (USD or SAR). Passed to the framework as `PortfolioContext(cash=…)` when execution is off, so the Portfolio Manager decides knowing the free cash. Screeners only suggest stocks where one share fits. **Leo's plan** is deterministic arithmetic, not a model call: weights Buy 2 / Overweight 1, × conviction (1.25/1/0.75), capped at 40% per stock with 3+ picks, whole shares at current Yahoo prices, FX via Yahoo. It states the buy list and the "not now" list explicitly with each verdict's reason.
73. **Beginner mode.** Amount + market (Saudi/US/both) + risk comfort → up to 5 large, well-known companies from a fixed, curated universe (steady vs growth), affordable at real prices and spread across sectors → full analysis → Leo's plan + a plain-language lesson with one tip per character, grounded only in the session notes (static general tips when no model is available). Education, not advice.
74. **Stop is immediate.** The graph stream runs in a worker thread; Stop ends the session in well under a second even mid model call. The worker stops at the next step and closes the checkpoint, so the run stays resumable. The bus ignores anything after `end`.
75. **No more hangs.** A failed voice line keeps the agent's full analysis and shows a fallback line; a failed verdict voice still publishes the verdict; any other failure still ends the session (and so the scan).
76. **The office is a staged film.** Ten sets follow what is playing (not what the server has finished): analyst close-ups, a debate arena where only Bolt and Bruno stay while the heat rises, Leo's office, the risk room, Albie's newsroom and the boardroom verdict. Characters walk to marks and step out, each has signature idle/thinking/speaking motion, listeners react, the camera pushes in on the speaker, title cards and an iris mark scene changes, and the speaker's face follows the tone of the line. Reduced motion turns all of it off.
77. **Accessibility:** text size (large / extra large), high contrast, read-aloud via the device's speech voice (lines wait until heard), a screen-reader live region for every line, keyboard shortcuts (`/` search, Space next line, Esc stop).
78. **Screens stay mounted** after the first visit (search results, open cards and typed text survive navigation); data screens refresh when shown again.
79. **Live board.** Yahoo's streaming feed (`wss://streamer.finance.yahoo.com`, the one yfinance's `WebSocket` uses) through one shared upstream connection, re-subscribed every 15 s, reconnecting with back-off; a 20 s snapshot poll fills symbols the stream hasn't updated for 90 s (closed markets, or no stream). Each quote carries its time and whether it came from the stream; the screen says "live" only for stream ticks under two minutes old. Browser updates are batched every 250 ms. Metals are COMEX/NYMEX futures; gold per gram in SAR (24K/21K) is calculated from gold and SAR=X and labelled as calculated. US open/closed prefers Yahoo's status (it knows holidays), Tadawul uses regular hours.
80. **Start-up speed.** (a) The desktop runtime and backend ship precompiled as "unchecked-hash" `.pyc` (valid after extraction changes file times); before, every `__pycache__` was stripped, so every launch recompiled thousands of modules (measured on Linux: full import 4.8 s → 2.2 s, server import 0.93 s → 0.42 s; Windows Defender scanning makes the saving larger there). (b) yfinance/pandas load on first use, and a background warm-up loads them and the framework right after the server is up. (c) Electron starts Python before its own window setup and polls readiness every 150 ms. (d) The recommended build is a per-user installer (`Veyro-Setup.exe`, no admin): the portable single exe unpacks ~340 MB on every launch, which no code change can avoid. Installed data lives in the user's app-data folder so it survives updates and uninstall.
81. **Reuse, not repay.** A finished real session for the same stock, date and models is offered again (single) or reused automatically in scans, replayed from the database with no model calls; reused sessions count in the scan's plan and ranking.
82. **Economy mode** is a free, deterministic price pre-screen (trend vs 50-day average ×2 + 3-month return − 0.3 × annualised volatility) that picks which stocks get the paid full analysis. It is labelled as a cost filter, not a recommendation; symbols without data go last.
83. **Virtual portfolio**: positions at the real price when added, compared with the regional benchmark from that moment; closing books the current price. Fees and dividends are not modelled (stated on screen). Adding reports honestly which symbols had no price.
84. **Price alerts** fire once, checked on every live tick and every 5 minutes by the scheduler; delivered through the existing alerts bell and Windows notifications.
85. **PDF** uses the system print dialog (Save as PDF), which renders Arabic right-to-left exactly as on screen; the button expands every section and waits for Arabic translations first.
86. **Data sources**: Yahoo (default), Stooq (free CSV, no key; US, indices, spot metals, FX; not Tadawul) and Alpha Vantage (owner's key; also switches TradingAgents' own vendors). Anything uncovered falls back to Yahoo and every price names its source. The Stooq and Alpha Vantage formats are unit-tested with sample responses; neither service was reachable from the build environment, so they still need a first real check.
87. **Free data only.** No subscriptions: Yahoo first, Stooq as an automatic free backup for what it covers (US, indices, spot metals, FX). Saudi benchmark: TASI when Yahoo has at least 20 days of its history, else the iShares MSCI Saudi Arabia ETF (KSA), which has full free history and tracks the market closely because the riyal is pegged to the dollar; the index actually used is stored with the session and passed to the framework.
88. **Trust dashboard**: deterministic, no model. A call is right when the stock beat (Buy/Overweight) or lagged (Underweight/Sell) its benchmark since the verdict; Hold is not scored. Shown by month, rating and model pair (with average cost), plus the virtual portfolio; a warning below 10 scored calls.
89. **Monthly budget cap**: counts the recorded cost of this month's real sessions (known prices only, and the UI says how many weren't priced). At the cap no new paid session, scan step, beginner run, morning report or backtest starts; a run that could cross it asks first. Demo is always allowed.
90. **Glossary**: 98 plain-language terms in six categories (basics, trading, technical, financials, economy, the team's calls) in both languages; the first mention of each term in reports, minutes and the beginner guide is tappable (at most 8 per block); a searchable glossary from the header.
91. **Second independent review (2026-09-25)** fixed: scans passing the budget-cap module instead of the budget (every multi-stock run failed; now covered by an end-to-end test), Stop ignored once the server had finished, an empty line freezing the dialogue, network work blocking the event loop in scan/replay endpoints, the live board re-subscribing the old market after a reconnect (and an orphan socket), closed paper positions' alpha drifting, the desktop app waiting 90 s after Python crashed, a late Stop recording a verdict, failed searches cached for an hour, a JSON-unescape path garbling Arabic, a typed company name ("apple") treated as a symbol, Saudi prices shown in dollars, and missing same-origin checks on local mutating endpoints and WebSockets.
