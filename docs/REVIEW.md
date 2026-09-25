# Veyro: end-to-end review (2026-09-25)

Branch `claude/affectionate-cerf-mjmt95`. Tested three ways: as a new user (Playwright on the real UI, Arabic and English, 1440 px and 390 px), as an equity analyst / PM (the financial code and its outputs), and as a senior engineer (code audit plus reproduction scripts).

**Labels.**
- **CONFIRMED**: reproduced here, by a test, a script or a screenshot.
- **INFERRED**: read from the code, not reproduced.
- **UNVERIFIED**: could not be tested here; the reason is given.

**Environment limits.** The sandbox cannot reach Yahoo, Stooq, exchange or regulator websites, Anthropic, or Electron on Windows. All UI flows used the stubbed test server (`tools/e2e/ui_server.py`: fake model, stubbed prices, fake live feed, stub fundamentals). Market rules and Sharia thresholds were checked with web search against the publishers' own domains; direct fetches of those sites were blocked (details in DECISIONS.md, entries 95 and 98).

---

## 1. Verdict

**Not ready for a real beginner to use with real money, anywhere.**

1. The core idea is good and honestly framed ("not financial advice" everywhere, Demo clearly labelled, execution off by default with typed confirmation). Engineering quality is above average for a solo app.
2. But the money advice is a set of single-stock picks with no index-fund option. Until today it could put 42% in one name against its own stated 40% cap. It still lets a single-stock report allocate ~98% of the budget to one company, and it ignores fees. The analysis itself can cost 1–2% of a SAR 1,000 budget before any broker fee.
3. The track-record numbers (trust dashboard) were scoring calls minutes old. They now wait for the holding period, but the sample will stay statistically meaningless for months. Nothing on screen shows a confidence interval.
4. "Global" is aspirational: two markets are hard-coded throughout: `.SR`, SAR/USD only, the NY date and clock, US-only screeners, and a US-only market-open chip.
5. Safe to use as a learning and thinking tool with paper money today. Real money needs the top items in §7 first.

---

## 2. Bugs

Severity reflects impact on money, safety or trust.

| # | Sev | Area | Status | Steps to reproduce | Fixed in |
|---|---|---|---|---|---|
| 1 | High | Security | CONFIRMED | A page on `attacker.example:8765` whose DNS points at 127.0.0.1 sends `Origin == Host`, so the same-origin check passes. `PUT /api/settings {"monthly_cap_usd":0}` returned 200 and cleared the cap. It can also start paid runs or change models. Test: `test_foreign_host_cannot_change_settings`, `test_foreign_host_websocket_refused`. | `479ebfa` (only loopback Host names are served, HTTP and WS) |
| 2 | High | Spend cap | CONFIRMED | Set a $1 cap. A session stopped just before the verdict after spending $2.40 is recorded as $0. A session with one unpriced model counts $0. Sessions still running aren't counted, so several started at once all pass. The framework backtest (up to 36 sessions) is never counted. Tests: `test_cancelled_session_cost_counts_toward_cap`, `test_partially_priced_session_counts_known_part`, `test_running_sessions_reserve_their_estimate`, `test_backtest_reserves_its_estimate`. | `41d24dc` |
| 3 | High | Allocation | CONFIRMED | Three Buys, $2,000 → AAPL gets 4 shares = $840 = **42%**, breaking the stated 40% cap (screenshot `verification/review/p3_ranking_plan_ar_1440.png`). The old unit test only checked `target`, not `cost`. Test: `test_plan_leftover_fill_respects_40_percent_cap`. | `02faf8c` |
| 4 | High | Beginner | CONFIRMED | Beginner → Both markets → SAR 1,000 → three Saudi stocks and no US stock. Coca-Cola was skipped as "same sector" as Almarai (`p1_beginner_picks_both_ar_390.png`). Tests: `test_beginner_both_markets_suggests_from_both` and e2e. | `8376fb6` |
| 5 | High | Stop | CONFIRMED | Press Stop while a voice line or Leo's verdict call is in flight: the cancelled `end` waits for that call, up to the client timeout. Measured 2.8 s on a 3 s stub. Test: `test_stop_does_not_wait_for_a_voice_call`. A verdict already recorded before Stop is still shown, so the UI matches History (`test_stop_after_verdict_recorded_still_shows_the_verdict`). | `2c0cf83` |
| 6 | Medium | Stop | INFERRED | A Stop during report export still wrote the decision into the framework's memory, which feeds later sessions. No automated test: it needs the full graph. | `2c0cf83` |
| 7 | Medium | Scans | CONFIRMED | Any exception in the scan loop (e.g. `database is locked`) killed the thread silently. The scan stayed `running` and its WebSocket waited forever. Test: `test_scan_that_hits_an_error_still_ends`. | `94cef46` |
| 8 | Medium | Keys | CONFIRMED | Save a key, run once, then Remove key. The key stayed in `os.environ`, still active and billable, and Settings showed it as present with source "env". Test: `test_removed_llm_key_is_no_longer_active`. | `c9afe01` |
| 9 | Medium | Trust | CONFIRMED | Three Buy calls a few minutes old with flat prices showed a **0% hit rate** (`p3_history_ar_1440.png`). Calls are now judged only after the framework's holding period (5 trading days ≈ 7 calendar days). Test: `test_trust_does_not_score_calls_minutes_old` and e2e. | `075414a` |
| 10 | Medium | History | CONFIRMED | History showed Saudi prices in dollars ("$27.50" for 2222.SR). The e2e check failed before the fix and passes after. | `075414a` |
| 11 | Medium | Morning report | CONFIRMED | Saudi favourites: the report was skipped every Sunday (a Tadawul trading day) and ran on Fridays (Tadawul closed), because it used New York's weekend. Test: `test_morning_report_runs_on_tadawul_sunday_not_friday`. | `381f213` |
| 12 | Medium | Paper portfolio | CONFIRMED | Close a position with no quote: it was booked at the entry price (an invented 0% result). Test: `test_closing_a_paper_position_without_a_price_is_refused`. | `ce7c872` |
| 13 | Medium | First run | CONFIRMED | A new visitor with an English browser got an Arabic-only welcome dialog that blocked the language button (`p0_first_run_*`). | `ce7c872` (follows browser language) |
| 14 | Low | Wording | CONFIRMED | Plan said "1 shares" / "6 سهم". The "Share" column (a money target) was easy to confuse with "Shares". | `ce7c872` |
| 15 | Low | Spend cap | INFERRED | The month boundary used local time while `created_at` is UTC: sessions between 00:00 and 03:00 on the 1st (UTC+3) fell outside both months. | `41d24dc` |
| 16 | Medium | Spend cap | INFERRED | Side LLM calls are never counted and don't check the cap: translate, verdict text, Albie's briefing/analyze/link, Ask the team, the beginner lesson (a **GET** with a paid side effect), and connection tests. Albie's in-session link also isn't in the session total. | Not fixed. Each is small (≈ one call), but they add up; needs a spend ledger fed by one shared tracker (§7 #3). |
| 17 | Medium | Spend cap | CONFIRMED (UI) | Non-Claude providers show "price unknown" (`p4_settings_other_provider_en_1440.png`), so the cap can't protect OpenAI/DeepSeek/etc. users. | Partly: the UI now says so plainly. A real fix needs a price table per provider (unverified prices were deliberately not guessed, decision 17). |
| 18 | High | Desktop | INFERRED | If the backend fails to start, closing the error splash leaves Electron running with no window and holding the single-instance lock. Every relaunch then does nothing until the process is killed. A Python backend that outlives a crashed Electron keeps the morning report (paid) running. | Not fixed: **UNVERIFIED**, Electron on Windows can't run here. Fix: quit on splash close after failure; a parent-PID watchdog in the backend. |
| 19 | Medium | Concurrency | INFERRED | Two runs of the same ticker, date and models share one LangGraph checkpoint thread (e.g. a single session plus a scan containing it). The second "resumes" the first's in-progress state. | Not fixed: needs a per-key run lock; low frequency. |
| 20 | Medium | Leaks | INFERRED | `/ws/live` lets any client add up to 120 symbols per message, never removed. Symbols with no data are re-polled every 20 s forever. The upstream stream keeps running with no clients. `BUSES`/`SCAN_BUSES`/`BACKTESTS` keep every event for the process lifetime, and the desktop app lives in the tray for days. | Not fixed; recommended: per-client symbol sets, pause the hub with no clients, prune buses minutes after `end`. |
| 21 | Low | Security | INFERRED | The execution Origin allowlist includes the Vite dev origins `:5173` in production. Any local dev server on 5173 could propose and confirm orders, within limits and only when Live is unlocked. | Not fixed; gate the dev origins behind an env flag. |
| 22 | Medium | Data honesty | INFERRED | `market.last_price` stamps `as_of` with *fetch time*, not quote time. With the market closed, "price at verdict" shows yesterday's close labelled as now. | Not fixed; label it "fetched at", or use the quote's own timestamp. |
| 23 | Low | UX | CONFIRMED | At 390 px the in-stage dialogue and verdict text scale to ~7–9 px and are unreadable (`p2_verdict_ar_390.png`). The full text is readable in the minutes below the stage. | Not fixed (design). |
| 24 | Low | Test harness | CONFIRMED | The e2e "price alert fires on a live tick" check waited a fixed 4 s while the fake feed ticks random symbols: it failed 1 time in 3. | `313c727` (polls up to 15 s) |

Checked and OK (INFERRED from code, several confirmed by the audit scripts):
- **Keys:** stored in the keyring only and masked in API responses. A log scrub filter is present, and no key reached the DB in tests.
- **Execution:** off by default. `submit` is reached only from `confirm()`, which needs a one-time token, the limits re-checked and `confirm: true`. Liquidation needs a typed phrase.
- **SQL:** parameterised everywhere; the f-strings only build code-controlled column names.
- **Paths:** static-file and export routes check against path traversal.
- **XSS:** no `dangerouslySetInnerHTML`; Markdown and glossary build React nodes.
- **SQLite:** a single connection, serialised with an RLock.
- **Caches:** the market and world caches are bounded.
- **WebSocket replay:** backlog and subscription are taken atomically, and the socket closes after `end`.

---

## 3. UX findings per persona

Screenshots are in `verification/review/`; the full run notes are in `notes_*.txt`. The walkthrough driver is `tools/e2e/review_personas.py`.

### 3.1 Complete beginner ("I have 1,000, what should I buy?")
- **Picks are named explicitly, with affordable whole-share counts, and currency is right on each row.** SAR 1,000 in Saudi gives Almarai, Ma'aden and stc, each ≥ 1 share. USD in the US gives KO, AAPL and PG. With SAR and both markets, the US prices are converted.
  - Screenshots: `p1_beginner_picks_both_ar_390.png` (before fix #4), `sharia_off_beginner.png`.
- **Friction: "Both" was Saudi-only** (fixed, #4).
- **Friction: the cost of the analysis is shown, but never compared with the amount.** A 3-stock beginner run is estimated at $1.68–$4.98, which is 0.6–1.9% of SAR 1,000, *before* any broker fee. A beginner doesn't know that's large (the budget bar in `p1_beginner_picks_both_ar_390.png` shows the estimate).
- **Missing:** an index-fund / ETF option. The universe is 26 single stocks, including NVDA and META as "growth" for someone with $267. The guide now at least explains index funds, time horizon, T+2/T+1 and price limits (`9fd5929`).
- **Wording (Arabic):** plural agreement fixed ("سهم واحد / سهمين / 5 أسهم"). The beginner hours line for the US assumes the reader lives in Saudi time ("afternoon to night in Saudi time") — wrong for anyone else (a global issue, §5).
- **Wording (English):** fine; "Target" replaces the ambiguous "Share" column.
- **Glossary:** terms are linked in the guide and the Report (e2e: 33 tappable terms in a report). 101 terms after this review.
- **Dead end (INFERRED):** after the guide, the only next step is "Run this plan on the virtual portfolio". There is no "how to actually buy this at a broker" step for someone who has never done it.

### 3.2 Retail investor (search by name, watch the film)
- **Search:** «ارامكو» → 2222.SR and "apple" → AAPL both work (`p2_search_ar_390.png`).
- **The film:**
  - Scene changes, the debate arena with only Bolt and Bruno, and the iris transitions all play.
  - Full untruncated text is in the minutes ("Full analysis").
  - Stop mid-run ends in 0.8 s (e2e). Stop at the very end is a no-op, and the verdict stays.
  - Leaving to Settings and coming back keeps the session playing (`p2_back_to_office_en_1440.png`).
- **Read-aloud is UNVERIFIED:** headless Chromium has no speech voices.
- **Friction:** at 390 px the film's dialogue and verdict text are too small to read (#23). The pixel font makes digits hard to read everywhere, e.g. "2222.SR" at small sizes.
- **Confusing:** the header chip "Market open" is the **US** market even on a Saudi stock's screen, while the beginner card says Tadawul is closed. Both are visible at once in `p1_beginner_picks_both_ar_390.png`.

### 3.3 Active investor
- **Watchlist + budget + economy pre-screen + reuse** all work (e2e `new_feats`: prescreen shown, only the top-N paid, reused session replays for free).
  - The pre-screen labels itself "not a recommendation", which is good.
- **Plan → virtual portfolio → close:** works. Closing without a quote is now refused (#12).
- **Price alert from the live board:** fires (e2e).
- **PDF:** the button exists; the print dialog itself is UNVERIFIED headless.
- **History, trust dashboard and spend:**
  - Before the fixes, History showed Saudi prices in $ and the trust dashboard "0% hit rate" from minutes-old calls (`p3_history_ar_1440.png`).
  - The spend meter and cap work; the cap now also sees stopped, running and backtest spend.
- **Missing:**
  - no per-position fees or dividends in the virtual portfolio (stated on screen);
  - no export of the paper portfolio;
  - no cost basis for multiple buys of one stock.

### 3.4 Settings power user
- **Models and prices:** every Claude model is listed with correct list prices, checked against Anthropic's price table. The recommended pair is marked (★ Sonnet 5 quick, ★ Opus 5.5 deep).
  - Switching to OpenAI shows its catalog and "price unknown" (`p4_settings_other_provider_en_1440.png`).
- **Data source switch:** saved (e2e). Stooq and Alpha Vantage themselves are UNVERIFIED (no network).
- **Accessibility:** extra-large text plus high contrast keep 390 px without horizontal scroll (`p4_office_xl_contrast_ar_1440.png`, `p4_settings_en_390.png`).
- **Orders:** "Execution is off, which is the default" with a friendly explainer (`p4_orders_en_1440.png`).
  - Minor: "Checking the risk limits…" stays visible as a stale loading line while execution is off.
- **Settings is long on mobile** (`p4_settings_en_390.png`): the cap, the Sharia section, the look settings and advanced items stack into a very long page. Consider tabs.

---

## 4. Financial-logic findings

| Issue | Why it matters for the user's money | Recommendation |
|---|---|---|
| **Single-stock and two-stock plans are uncapped** (decision 72: the 40% cap applies only with 3+ picks). A single-stock report puts ~98% of the budget in one company (`sharia_on_report.png`: 14 × AAPL = $2,940 of $3,000). | One name can halve; a beginner reads "The team recommends buying" as "put it all in". | Cap every name at 40% (or 25% for beginners) and keep the rest as cash, or show "this is one stock, not a portfolio" loudly. Owner decision: not changed silently. |
| **Weights: Buy 2, Overweight 1, × conviction.** Conviction is an LLM's reading of LLM text, labelled honestly. | Weights express the model's enthusiasm, not risk. Two correlated tech Buys get 80% together. | Add inverse-volatility sizing (free from price history), a sector cap (e.g. 50%), and a correlation check (60 days of daily returns). |
| **No fees, spread or FX cost** in the plan. | On SAR 1,000, a minimum-commission broker can take several percent. The plan's "cash left" is not what the user would have. | Add a "fees" field (default 0.155% + 15% VAT for Tadawul is the commonly cited cap, **unverified primary**; $0 for most US brokers) plus a cash buffer, e.g. 2%. |
| **The analysis cost isn't compared with the budget.** | $5 of LLM cost on $267 is 1.9%, like a very bad fund fee. | Warn when the estimated cost is over 0.5% of the amount; suggest Haiku or economy mode. |
| **No index-fund path for beginners.** | The single most useful advice for a $1,000 beginner is missing. | Add broad-market ETFs to the universe with a plain "the simplest option" card (fundamentals-less, as crypto already is). |
| **Trust dashboard** (fixed: holding-period wait). Remaining issues: calls are scored "since the verdict until now", so ages differ; duplicates of the same ticker count as independent; the hit rate has no uncertainty; dividends are ignored on both sides (price vs price index: consistent but not total return). | 10 calls at 60% hit rate has a 95% interval of roughly 30–85%: it proves nothing. | Score at a fixed horizon (e.g. 5 and 20 trading days) using `close_on_or_before`; show the Wilson interval; raise the minimum sample to 30; dedupe same-ticker same-week calls. |
| **Virtual portfolio**: P&L and alpha from entry to now are computed correctly; the benchmark window matches (frozen at close). Ignores dividends, fees and FX (USD positions for a SAR user). Survivorship: a delisted ticker returns no price → value unknown, and the total becomes "unknown" (honest). | Overstates returns relative to reality by the fees; understates them for high-dividend Saudi stocks. | Add a fees setting and a dividend toggle (yfinance `dividends` is free); show the SAR-equivalent P&L for a SAR user holding USD. |
| **Pre-screen** score = 2×trend + 3-month return − 0.3×vol. | Pure momentum: it sends the stocks that already ran up to the paid analysis. Defensible as a *cost filter* (labelled so), not as selection. | Offer a "quality/value" alternative from free data: 12-1 month momentum (skip last month), 52-week-high distance, dividend yield, P/E vs sector. Show which filter was used. |
| **Benchmarks**: `.SR` → `^TASI.SR` (KSA fallback), US → SPY. | Reasonable. KSA is a USD ETF of *large and mid* Saudi caps, not TASI; the peg makes currency noise small, but composition differs. | Store which benchmark was used (already done). For new markets use the local broad index, or its most liquid ETF when Yahoo's index history is short. |
| **Data quality**: `as_of` is fetch time (#22); stale closed-market quotes look live on the verdict; `auto_adjust=False` history is split-adjusted but not dividend-adjusted (fine for price comparisons); NaN rows are dropped; holidays aren't modelled (Tadawul/US status uses regular hours only). | A user may act on "price now" that is yesterday's close. | Show the quote's own time; add the exchange holiday calendars (free: exchange websites; `pandas_market_calendars` covers NYSE and others). |
| **Risk communication**: disclaimers are everywhere and not buried. The bold green "✅ The team recommends buying" plus "BUY" plus confetti overstates confidence for a model-generated call. | Beginners anchor on the big word. | Show conviction and "how often calls like this were right (n=…)" next to the verdict word; tone down confetti for real money. |

---

## 5. Global readiness

**Hard-coded to Saudi/US (found by grep and reading):**
- Suffix `.SR` special cases in about 48 backend places, e.g. `beginner`, `runner.benchmark_for`, `priceText`, `live`, `allocation`, `extras`.
- Currency: `("USD","SAR")` whitelists in `app._budget`, `_beginner_args` and the `Budget` type. GBp/pence (London) and other minor units are not handled anywhere.
- Time:
  - `runner.ny_today()` is the analysis date for **every** market; a Tadawul stock on Sunday morning is analysed "as of" New York's Saturday;
  - the date picker's max is NY;
  - `Room.tsx` clock is New York;
  - the morning report used NY weekends (fixed).
- Hours: only in `beginner.MARKETS` (sa/us). The header market chip is US-only (`yf.Market("US")`).
- Screeners: `market.screen` drops any symbol containing "." (US only). There is no Saudi scan.
- Aliases: Arabic aliases are Saudi and US names only.
- Beginner universes: sa/us only. The US hours text assumes a reader in Saudi time.
- Execution: US equities only (Alpaca), which is correct for now.

**Proposed per-market config** (one file, `backend/veyro/markets.py`, served to the UI):
```python
MARKETS = {
  "sa":  {"exchange": "Tadawul", "suffix": ".SR", "currency": "SAR", "minor_unit": None, "tz": "Asia/Riyadh",
          "days": (6,0,1,2,3), "sessions": {"open": "10:00", "close": "15:00", "auction": ("15:00","15:10")},
          "holidays": "calendars/xsau.json", "benchmark": "^TASI.SR", "benchmark_fallback": "KSA",
          "price_limit": 0.10, "settlement": "T+2", "tick_table": [...], "fees": {"commission": None, "vat": None},  # unverified -> None
          "universe": [...], "screener": "yf.screen(EquityQuery('eq',['exchange','SAU']))", "names": {"ar": ..., "en": ...}},
  "us":  {...}, "uk": {"suffix": ".L", "currency": "GBP", "minor_unit": "GBp", "tz": "Europe/London", "benchmark": "^FTSE", ...},
}
def market_of(symbol) -> str  # by suffix; "" -> "us"
```
Everything above (the analysis date in the market's own time zone, the open/closed chip per market, benchmark, affordability FX, tips, universe, screeners) reads from it. Unverified fields stay `None` and the UI says "not available" rather than guessing.

**Effort to add a market (free data only):**

| Market | Yahoo suffix | Benchmark (free) | Extra work | Effort |
|---|---|---|---|---|
| UAE (ADX/DFM) | `.AD` / `.AE` | FTSE ADX (thin on Yahoo) → iShares UAE ETF (UAE) | Two exchanges, AED pegged | M |
| Egypt | `.CA` | EGX30 (`^CASE30`) | EGP volatility makes FX essential; data gaps | M |
| UK | `.L` | `^FTSE` / ISF.L | **Pence (GBp) quotes**: must divide by 100 everywhere; 0.5% stamp duty | M |
| EU | `.PA` `.DE` `.AS`… | `^STOXX50E` / country indices | Many exchanges and holidays; EUR | M–L |
| India | `.NS` / `.BO` | `^NSEI` | Circuit limits per stock band, T+1, lot sizes | M |
| Japan | `.T` | `^N225` (already in the framework's map) | **100-share trading units**: whole-share maths must use lots | M |

The core refactor (config and all call sites) is **M** (about 2–4 days). Each market after that is S–M for the data, plus verification of its rules from primary sources.

**Localisation beyond ar/en:**
- Numbers use Latin digits in Arabic (a deliberate, readable choice), and dates use the Gregorian calendar.
- Currency formatting is hand-rolled (`SAR 27.50` / `27.50 ريال`) instead of `Intl.NumberFormat(locale, {style:"currency"})`, which would make new currencies free.
- RTL: mixed LTR tickers inside Arabic sentences render correctly (`ltr` spans).
- Adding a third language means touching every inline `lang === "ar" ? … : …` ternary: there are hundreds. Move them into the i18n dictionary before adding languages.

---

## 6. Sharia screening

**Methodology and sources:** DECISIONS.md, entries 97–104.
- **Default is AAOIFI Shari'ah Standard No. 21**: debt ≤ 30% and interest-bearing deposits ≤ 30% of market cap; non-permissible income ≤ 5% of revenue. The 5% could only be confirmed from secondary quotations, and this is stated.
- **Alternatives:** S&P Shariah (36-month average market cap; 33% / 33% / 49% receivables) and MSCI Islamic (total assets; 33.33% for debt, cash, and receivables + cash).
- **Exclusions:** the core activity exclusions apply to all three methods. S&P and MSCI add their own documented extra exclusions.

**Built:**
- Backend: `backend/veyro/sharia.py`.
- UI: `frontend/src/extras/Sharia.tsx`.
- Tests: 33 unit tests (`backend/tests/test_sharia.py`) and 14 Sharia checks in the e2e suite `tools/e2e/review_fixes.py`.

**Data coverage per market: UNVERIFIED** (Yahoo blocked here). What *was* confirmed is the fail-safe: with no data, all 34 stocks in the SA/US universe and alias list came out **Unknown (no_data), none Compliant**. Run `.venv/bin/python tools/sharia_coverage.py [aaoifi|sp|msci]` on a connected machine to get the real table. Expected, from how the rules work (INFERRED):
- **Saudi:**
  - Al Rajhi, Alinma, Albilad and Aljazira: **Unknown** by design (Islamic banks; their boards certify them).
  - SNB, Riyad Bank and other conventional banks: **Not compliant** by industry.
  - Tadawul balance sheets on Yahoo are sometimes annual-only, so data may be up to ~15 months old, still under the 18-month stale limit.
- **US:**
  - JPM: **Not compliant** (bank).
  - V (Credit Services): **Unknown** (ambiguous industry).
  - Most large tech: likely Compliant under AAOIFI but may fail the cash ratio (large cash piles; e.g. companies holding big short-term investments).
  - Interest income is often missing on Yahoo, which gives "income not checked".

**Known limitations:**
- Industry-level activity mapping, not revenue segments: a 3% alcohol sideline passes and a 6% one isn't seen.
- The only non-permissible income visible in free data is interest income.
- The S&P 36-month average market cap uses today's share count.
- MSCI's 4-quarter averaging and entry/exit buffers are not implemented.
- Total Debt from Yahoo includes leases; conservative, but it can fail a borderline company.
- Cash + short-term investments is treated as interest-bearing, which is also conservative.
- Yahoo industry names change over time; unknown names fall through to the ratio tests, and only listed ambiguous names become Unknown.
- The Islamic-bank list is Saudi-only (4 names).
- It's an estimate, never a fatwa. The disclaimer is shown on every Sharia surface.

---

## 7. Top 10 feature wishes (ranked by value ÷ effort)

| # | What | Who it helps | Effort | Free data only? |
|---|---|---|---|---|
| 1 | **Index-fund path for beginners**: a "simplest option" card with a broad ETF (e.g. an S&P 500 ETF; a Saudi or MSCI Saudi ETF), analysed with fundamentals skipped as crypto is | Every beginner | S | Yes |
| 2 | **Cost-vs-budget warning**: "this analysis costs ~1.9% of your amount; try Haiku or economy mode" | Small budgets | S | Yes |
| 3 | **One spend ledger** fed by a shared usage tracker for every LLM call (translate, ask, Albie, lesson, tests), checked before each paid call | Anyone with a cap | S–M | Yes |
| 4 | **Per-market config** (§5), with the analysis date in the market's own time zone and a per-market open/closed chip | Global users, Saudi users today | M | Yes |
| 5 | **Fees and cash buffer in the plan** (per-market fee fields, broker minimums), and whole-share *lots* where needed | Anyone buying for real | S | Yes (fees entered by the user) |
| 6 | **Risk-aware sizing**: inverse-volatility weights, sector cap, correlation warning, and the 40% cap for 1–2 picks too | Active investors | M | Yes |
| 7 | **Fixed-horizon track record** (5 and 20 days) with a Wilson interval and n ≥ 30 before showing a headline hit rate | Everyone deciding whether to trust the team | S | Yes |
| 8 | **Exchange holiday calendars** and the quote's real timestamp everywhere | Everyone | S–M | Yes (exchange sites, `pandas_market_calendars`) |
| 9 | **Dividends and total return** in the virtual portfolio and trust dashboard | Saudi income investors especially | M | Yes (yfinance dividends) |
| 10 | **"How to buy this" step**: a broker-agnostic checklist (order type, limit vs market, T+2/T+1, fees), with an optional Sharia-compliant broker/fund note | First-time buyers | S | Yes |

---

## 8. Verify on your real machine (live data)

- [ ] `tools/sharia_coverage.py aaoifi|sp|msci`: coverage table per market; spot-check 5 results against an official list (e.g. your broker's Sharia list).
- [ ] Yahoo quotes for `.SR` symbols: correct currency (SAR), previous close, delay. Compare "price at verdict" with Tadawul's site.
- [ ] `^TASI.SR` history length: whether TASI or the KSA fallback is used, as recorded in the session.
- [ ] Live board: the stream connects, ticks carry real times, "live" shows only for fresh ticks; behaviour at Tadawul close and on a US holiday.
- [ ] Stooq and Alpha Vantage sources (DECISIONS 86 says they were never reachable during the build).
- [ ] A full real Claude session: cost recorded, and Stop mid-voice-line ends in < 1 s (fix #5), then the cost appears in the month's spend (fix #2).
- [ ] Set a small cap (e.g. $0.50), start a watchlist of 3: the second session must not start once the reservation passes the cap.
- [ ] Remove the Anthropic key in Settings, then try a session: it must say "no key" at once (fix #8).
- [ ] Morning report on a Sunday with Saudi favourites (fix #11).
- [ ] Desktop: kill `python.exe` at start-up, then close the error splash and relaunch; confirm whether Veyro reappears (finding #18, not fixed).
- [ ] Desktop: kill the Electron process; confirm whether `python.exe` stays alive (finding #18).
- [ ] PDF export in Arabic and English (print dialog → Save as PDF).
- [ ] Read-aloud voices on Windows for Arabic and English.
- [ ] Alpaca Paper: propose → confirm → fill, and that nothing submits without confirm.
- [ ] Market rules shown in the beginner tips against saudiexchange.sa and nyse.com (hours, ±10%, T+2 / T+1, circuit breakers).
- [ ] Tadawul fees for your broker (commission and VAT), which the app deliberately does not state.

---

## 9. Test counts

| Suite | Before | After |
|---|---|---|
| Backend pytest (`backend/tests`) | 42 passed | **93 passed** (+18 regression tests in `test_review_fixes.py`, +33 in `test_sharia.py`) |
| e2e `ui_test` | 12 PASS | 12 PASS |
| e2e `new_feats` | 14 PASS | 14 PASS (alert check made deterministic) |
| e2e `round3` | 5 PASS | 5 PASS (glossary 98 → 101 terms) |
| e2e `review_fixes` (new) | — | 20 PASS |
| TypeScript `tsc --noEmit` and `npm run build` | OK | OK |

Totals: pytest **42 → 93**, browser checks **31 → 51**, 0 failures in the final run (`tools/e2e/run_all.sh`, 2026-09-25).
