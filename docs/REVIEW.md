# Veyro: end-to-end review (2026-09-25)

Branch `claude/affectionate-cerf-mjmt95`. Tested three ways: as a new user (Playwright on the real UI, Arabic and English, 1440 px and 390 px), as an equity analyst / PM (the financial code and its outputs), and as a senior engineer (code audit plus reproduction scripts).

**Labels.**
- **CONFIRMED**: reproduced here, by a test, a script or a screenshot.
- **INFERRED**: read from the code, not reproduced.
- **UNVERIFIED**: could not be tested here; the reason is given.

**Environment limits.** The sandbox cannot reach Yahoo, Stooq, exchange or regulator websites, Anthropic, or Electron on Windows. All UI flows used the stubbed test server (`tools/e2e/ui_server.py`: fake model, stubbed prices, fake live feed, stub fundamentals). Market rules and Sharia thresholds were checked with web search against the publishers' own domains; direct fetches of those sites were blocked (details in DECISIONS.md, entries 95 and 98).

---

## 1. Verdict

*Updated after the second round (every recommendation implemented, see "Second round" below). The first-round verdict is kept in git history.*

**Much safer as a learning tool; still not something a beginner should follow with real money without their own judgement.**

1. The money logic is now defensible:
   - every stock is capped at 40% and every sector at 50%;
   - weights account for volatility, and look-alike pairs are flagged;
   - fees you enter are deducted, and the plan says plainly when they aren't entered;
   - beginners see a no-analysis index-fund option first;
   - a warning appears when the analysis costs more than 0.5% of the amount.
2. The track record is honest: it is scored at fixed 5/20-session horizons with a 95% range, "too few to judge" is shown under 30 calls, and the verdict shows how often past calls of that kind were right. It will still be statistically meaningless for months, and the app now says so.
3. The core risk hasn't changed: a "Buy" is an LLM's reading of free data. It isn't personal advice, it doesn't know your finances, and it has no proven edge yet.
4. Two markets only, by the owner's choice. The Saudi/US specifics are now handled correctly in place: local dates, holidays, per-market status and honest quote times.
5. Real money still needs the live-data checks in §8, especially prices, fees and the Sharia coverage on your own machine.

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
| 16 | Medium | Spend cap | INFERRED | Side LLM calls are never counted and don't check the cap: translate, verdict text, Albie's briefing/analyze/link, Ask the team, the beginner lesson (a **GET** with a paid side effect), and connection tests. Albie's in-session link also isn't in the session total. | `84e7a9d` (one spend ledger; side calls counted per reply and refused at the cap; beginner guide is POST) |
| 17 | Medium | Spend cap | CONFIRMED (UI) | Non-Claude providers show "price unknown" (`p4_settings_other_provider_en_1440.png`), so the cap can't protect OpenAI/DeepSeek/etc. users. | `41d24dc` (UI says so) + `84e7a9d` (the owner can enter a model's price; then the estimate and cap count it) |
| 18 | High | Desktop | INFERRED | If the backend fails to start, closing the error splash leaves Electron running with no window and holding the single-instance lock. Every relaunch then does nothing until the process is killed. A Python backend that outlives a crashed Electron keeps the morning report (paid) running. | `c5d4ee7`: the error screen has Close and closing quits; the backend watchdog exits when Electron dies (watchdog tested here; the Electron part is **UNVERIFIED**, `node --check` only) |
| 19 | Medium | Concurrency | INFERRED | Two runs of the same ticker, date and models share one LangGraph checkpoint thread (e.g. a single session plus a scan containing it). The second "resumes" the first's in-progress state. | `12a50a6` (a duplicate Start attaches to the running session; a fresh start waits while a stopped run finishes) |
| 20 | Medium | Leaks | INFERRED | `/ws/live` lets any client add up to 120 symbols per message, never removed. Symbols with no data are re-polled every 20 s forever. The upstream stream keeps running with no clients. `BUSES`/`SCAN_BUSES`/`BACKTESTS` keep every event for the process lifetime, and the desktop app lives in the tray for days. | `4f3b37f` (upstream = base + open screens + alerts, ≤ 200 extra; failing symbols back off; hub pauses with nobody watching; session buses pruned after 30 min and rebuilt on demand) |
| 21 | Low | Security | INFERRED | The execution Origin allowlist includes the Vite dev origins `:5173` in production. Any local dev server on 5173 could propose and confirm orders, within limits and only when Live is unlocked. | `4f3b37f` (`VEYRO_DEV=1` only) |
| 22 | Medium | Data honesty | INFERRED | `market.last_price` stamps `as_of` with *fetch time*, not quote time. With the market closed, "price at verdict" shows yesterday's close labelled as now. | `5328c31` (a closed-market quote is dated as that session's close; the verdict shows "close of …") |
| 23 | Low | UX | CONFIRMED | At 390 px the in-stage dialogue and verdict text scale to ~7–9 px and are unreadable (`p2_verdict_ar_390.png`). The full text is readable in the minutes below the stage. | `139c4a5` (under 700 px the dialogue and verdict render under the stage at 16–17 px) |
| 24 | Low | Test harness | CONFIRMED | The e2e "price alert fires on a live tick" check waited a fixed 4 s while the fake feed ticks random symbols: it failed 1 time in 3. | `313c727` (polls up to 15 s) |
| 25 | Medium | Relay | CONFIRMED | With Anthropic unreachable, the relay raised before closing its HTTP client (leak and a 500). Test: `test_relay_closes_its_client_when_anthropic_is_unreachable`, which fails before the fix. | `4f3b37f` (closes the client, answers 502) |
| 26 | Low | Orders | CONFIRMED | "Checking the risk limits…" on the Orders screen was Tank's speech bubble, not a stuck loader as I first wrote. It still claimed checks while execution was off. | `139c4a5` |

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

| Issue | Why it matters for the user's money | What was done (second round) |
|---|---|---|
| **Single-stock and two-stock plans were uncapped** (decision 72). A single-stock report put ~98% of the budget in one company (`sharia_on_report.png`). | One name can halve; a beginner reads "The team recommends buying" as "put it all in". | `bb1169f`: 40% cap on every stock always; the rest stays in cash with "one or two stocks are not a diversified portfolio" (e2e `round4`). |
| **Weights: Buy 2, Overweight 1, × conviction.** | Weights expressed the model's enthusiasm, not risk; two correlated tech Buys could get 80%. | `bb1169f`: × inverse volatility (clipped ×0.5–×2), 50% sector cap, correlation > 0.8 flagged (unit tests in `test_allocation_risk.py`). |
| **No fees** in the plan. | On small amounts a minimum commission can take several percent. | `bb1169f`: owner-entered fees per market (rate, minimum, VAT) are deducted; the plan says when they aren't entered. No default: the Tadawul cap and VAT treatment are unverified. |
| **The analysis cost wasn't compared with the budget.** | $5 on $267 is 1.9%. | `6c8737c`: a warning above 0.5% of the amount, suggesting Haiku, economy mode or the index fund. |
| **No index-fund path for beginners.** | The most useful advice for a $1,000 beginner was missing. | `6c8737c`: 9412.SR / SPYM / VT card with the units your amount buys, no paid analysis, one click to the virtual portfolio. |
| **Trust dashboard** scored "since the call until now", counted duplicates, showed no uncertainty. | 10 calls at 60% has a 95% range of about 31–83%. | `1441abe`: 5- and 20-session horizons in each market's calendar, duplicates within 5 days counted once, Wilson interval, minimum 30, and the verdict shows the track record. |
| **Virtual portfolio** ignored fees, dividends and currency. | Overstated returns by the fees; understated them for dividend payers. | `f2c57de`: fees in and out, dividends while held (fund benchmarks too), and a combined USD total including currency moves. |
| **Pre-screen** was pure momentum. | It sent what had already run up to the paid analysis. | `f2c57de`: a "steady" mode (12-1 month return − volatility − worst drop). Value/quality factors (P/E, dividend yield) were not added: they need per-company fundamentals per candidate, which is slow with free data. |
| **Benchmarks**: `.SR` → `^TASI.SR` (KSA fallback), US → SPY. | Reasonable; KSA ≠ TASI in composition. | Unchanged (sound). The benchmark used is stored per session. |
| **Data quality**: fetch-time `as_of`, no holidays. | A closed-market price looked live. | `5328c31`: closed-market quotes dated as that session's close; XSAU/XNYS holiday calendars. Split/dividend adjustment unchanged (consistent price-vs-price-index). |
| **Risk communication**: the bold "BUY" with confetti overstated confidence. | Beginners anchor on the big word. | `1441abe`: no confetti on real-money verdicts, and the track record sits next to the verdict word. |

---

## 5. Global readiness

**Owner decision (second round):** keep each market as it is, with no per-market config refactor for now (DECISIONS 105). Fixed in place instead (`5328c31`):
- the analysis date is the stock's own market date;
- the header shows Tadawul and US separately;
- the office clock follows the stock's market;
- holidays come from XSAU and XNYS calendars;
- a closed-market quote is dated as that session's close;
- the English US hours no longer assume a reader in Saudi time.

The refactor below is still what a *third* market would need.

**Hard-coded to Saudi/US (found by grep and reading; the date, clock and status items are fixed as above):**
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

All ten were built in the second round except #4, which the owner decided against; the markets were fixed in place instead.

| # | What | Who it helps | Effort | Free data only? | Status |
|---|---|---|---|---|---|
| 1 | Index-fund path for beginners | Every beginner | S | Yes | Done, `6c8737c` (a card, no analysis; not run through the framework) |
| 2 | Cost-vs-budget warning | Small budgets | S | Yes | Done, `6c8737c` |
| 3 | One spend ledger for every model call | Anyone with a cap | S–M | Yes | Done, `84e7a9d` |
| 4 | Per-market config | A third market | M | Yes | **Not built (owner decision)**; the market bugs were fixed in place, `5328c31` |
| 5 | Fees in the plan | Anyone buying for real | S | Yes (fees entered by the user) | Done, `bb1169f`; trading lots not needed for Tadawul/US |
| 6 | Risk-aware sizing | Active investors | M | Yes | Done, `bb1169f` |
| 7 | Fixed-horizon track record with uncertainty | Everyone | S | Yes | Done, `1441abe` |
| 8 | Holiday calendars and honest quote time | Everyone | S–M | Yes | Done, `5328c31` (`exchange_calendars`) |
| 9 | Dividends and total return | Income investors | M | Yes | Done in the virtual portfolio, `f2c57de`; the trust dashboard stays price vs price index (consistent on both sides) |
| 10 | "How to buy this" step | First-time buyers | S | Yes | Done, `6c8737c` (broker-neutral; no broker is named or rated) |

**Next wishes, not built:**
- A Saudi market scan: Yahoo's predefined screeners are US-only, and a custom `EquityQuery` for Tadawul can't be tested here.
- Value/quality pre-screen factors.
- Moving inline Arabic/English strings into the dictionary before any third language.
- `Intl` currency formatting for new currencies.

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
- [ ] Desktop: make `python.exe` fail at start-up; the error screen must show a Close button, closing it must end Veyro, and a relaunch must open again (fix #18).
- [ ] Desktop: kill the Electron process in Task Manager; `python.exe` must exit within a few seconds (fix #18 watchdog; Windows path not run here).
- [ ] Holidays: on a Tadawul or US holiday, the header shows that market closed (`exchange_calendars` must be installed: re-run `pip install -r backend/requirements.txt` on an existing install).
- [ ] 9412.SR, SPYM and VT quotes on Yahoo: the index-fund card shows prices (else "unavailable").
- [ ] Enter your broker's real fees in Settings → Broker fees and check one plan's fee against your broker's own calculator.
- [ ] Dividends in the virtual portfolio for a Saudi dividend payer (e.g. 2222.SR) after an ex-date.
- [ ] Settings → model price for a non-Claude model: after one session, the month's spend includes it.
- [ ] PDF export in Arabic and English (print dialog → Save as PDF).
- [ ] Read-aloud voices on Windows for Arabic and English.
- [ ] Alpaca Paper: propose → confirm → fill, and that nothing submits without confirm.
- [ ] Market rules shown in the beginner tips against saudiexchange.sa and nyse.com (hours, ±10%, T+2 / T+1, circuit breakers).
- [ ] Tadawul fees for your broker (commission and VAT), which the app deliberately does not state.

---

## 9. Test counts

| Suite | Baseline | After round 1 | After round 2 | After round 3 |
|---|---|---|---|---|
| Backend pytest (`backend/tests`) | 42 | 93 | 121 | **138** |
| e2e `ui_test` | 12 | 12 | 12 | 12 |
| e2e `new_feats` | 14 | 14 | 14 | 14 |
| e2e `round3` | 5 | 5 | 5 | 5 |
| e2e `review_fixes` | — | 20 | 20 | 20 |
| e2e `round4` | — | — | 14 | 19 (value mode, US and Saudi) |
| e2e `persist` | — | — | — | 12 (every screen keeps its state) |
| e2e `stop` | — | — | — | 9 (Stop is immediate) |
| e2e `fun` | — | — | — | — (round 4: 26, easter eggs and label overlap) |
| e2e `round5` | — | — | — | — (round 4: 9, frontend review fixes) |
| TypeScript `tsc --noEmit` and `npm run build` | OK | OK | OK | OK |

Totals after round 3: pytest **42 → 138**, browser checks **31 → 91**, 0 failures in the last full run of `tools/e2e/run_all.sh`.
Round 4: pytest **158** (5 Saudi scan + 15 review fixes); browser checks **92 + 26 + 9 = 127**, 0 failures in the full run of `tools/e2e/run_all.sh` (9 suites).

## Round 3 (owner requests)

**Value pre-screen for Saudi and US stocks** (`9208f1f`):
- It compares P/E with the company's own sector in its own market; a sector with fewer than 3 peers is compared with the whole market, and the line says so.
- Dividend yield is computed from the dividends actually paid.
- Loss-making companies and missing data go last with the reason.
- Details are in DECISIONS 120.

**Screens keep their state** (`3fd78a3`). A test fills in every screen, tours all screens twice and comes back. It found one real gap: the scroll position was lost, and the header scrolled away so you had to scroll up to change screens. Both are fixed.

**Stop is immediate** (`5f629c4`). Measured in the browser, 0.08–0.30 s in every state: right after Start, mid-run in single, watchlist and beginner modes, and by Esc. Right after Start used to take 7.84 s. There were two causes:
- nothing checked for Stop during start-up;
- the Start button waited for Leo's "stopped" line to finish.


## Round 4 (owner: «قم بااتمام الباقي… وتأكد من فحص المشاكل», plus the easter eggs)

Two independent reviews of everything changed on this branch (backend and frontend, read-only), then every finding was checked. The fixes below are **CONFIRMED**: each has a test that failed on the code before the fix and passes after it. The exceptions are marked.

**Backend** (`backend/tests/test_round4_backend.py`, 15 tests):

| # | Finding | Fix |
|---|---|---|
| 1 | A run cut off by closing the app (or the parent watchdog) counted **$0** against the monthly cap after the next start | Usage is written to the database after every model reply; running sessions reserve the rest of their estimate |
| 2 | Model calls that finished after Stop never reached the database | Same write-through: the late reply updates the recorded cost |
| 3 | The start check didn't count the run about to start ($2 cap, $1.66 reserved → a second start was allowed) | Refused when spent + reserved + this run's high estimate would pass the cap |
| 4 | Splits and bonus shares: a Buy before a 4-for-1 split scored as a 74% loss; a paper position showed −74.75% | The track record and the virtual portfolio multiply by the split factor since the call/purchase |
| 5 | The lead over ^TASI.SR (a price index) counted the stock's dividends: flat prices + 3 dividends = "+4.9%" | Against a price index the lead uses price only; the total return still includes dividends and the UI says so |
| 6 | Saudi cooperative (takaful) insurers came out "not compliant" | "Unknown: its own Sharia board decides" |
| 7 | A 5-session horizon ending today was scored with the day before's close | It waits for that day's close |
| 8 | US early-close days (13:00) showed "open" until 16:00 | The calendar's own hours for that day |
| 9 | With fees entered for one market only, a mixed plan dropped the "fees not entered" note | The note names the market without fees |
| 10 | A scan that joined someone else's run of the same stock left it out of its results and plan, and stopping the scan cancelled it | Listed as the scan's result; stopping the scan only stops following it |
| 11 | A backtest on a model with no known price was recorded as $0 | Counted as unpriced |
| 12 | The owner's price for a model didn't match the dated name providers reply with | Same prefix rule as the built-in table |
| 13 | BTCUSD and BTC-USD got separate run locks for the same framework checkpoint | One lock per instrument |

**Frontend** (`tools/e2e/round5.py`, 9 browser checks; 6 of the 7 failed before the fix):

| # | Finding | Fix |
|---|---|---|
| 1 | Selling a paper position with no current price did nothing | It says the position stays open and why |
| 2 | Pressing Save on an untouched custom model price deleted it | Untouched fields keep the saved price (INFERRED; no browser check, fixed by reading) |
| 3 | Fee fields rejected Arabic digits (٠٫١٥٥) | Accepted |
| 4 | Report section jumps landed under the sticky header and menu (−150 px at 1100 px wide) | Offset by the header and the menu's real height |
| 5 | The cost estimate ignored economy mode ($3.36–$9.96 for 6 stocks while only the best 2 were analysed) | Recomputed every render: $1.12–$3.32 |
| 6 | Index fund: "buys 0 units ($0)" | "isn't enough for one unit"; singular/plural in both languages |
| 7 | Phone: the dialogue box grew sideways letter by letter (123 px → full width) | Full width from the first letter |
| 8 | Live → Analyse returned to the Office's old scroll spot | **Not reproduced**: the search box's focus already scrolls to the top. A safeguard was kept |
| 9 | Hidden (non-compliant) scan candidates still counted in the estimate; a scan stopped before its first session still jumped into it; the US clock went grey when Yahoo was down; a past-date verdict said "market closed"; a Sharia badge could stay on "checking"; late answers could overwrite a newer choice (beginner picks, screener preview) | Fixed by reading both sides (INFERRED; no browser check) |
| 10 | Desktop: the error screen could open in the hidden main window while the splash spun forever; a timeout's exit replaced the real cause; taskkill could hit a PID Windows had reused | Error shown in the visible window; one error screen; no taskkill after the process has exited. **UNVERIFIED**: Electron on Windows can't run here |

**Checked and not reproduced** (measured in the browser, nothing changed):
- The one-row header overflowing at 1260 px in Arabic. Measured at 900, 1100, 1259, 1260, 1300 and 1440 px in both languages: no horizontal scroll and no item outside the header.
- The verdict box being clipped with the Sharia panel and track record. With the screen on, a Buy on 7010.SR at 1440 and 1100 px has its bottom 14–15 px inside the stage, and the disclaimer is visible.

**Owner's layout report:** Bolt's horns covered Buzz's role label and Bruno's head covered Leo's. A check of every name and role label against every other character's sprite found 5 overlaps in the old layout (Ollie, Buzz, Pip, Benny and Leo each had a label covered). The back row now sits 20 px lower and labels are drawn above characters: 0 overlaps in Arabic and English.

**Easter eggs** (DECISIONS 125; `tools/e2e/fun.py`, 26 checks):
- jokes when you tap a character, and a special line after five taps;
- idle chatter;
- party mode (Konami code, or five taps on the wall clock);
- Bruno walks into the risk room and says **«ورع، لا تشتري هذا!»** when the risk team clearly warns, and again at a Sell call.
- The tests also check the cases where Bruno must stay quiet: never at a Buy or Hold call, and never for a risk line that isn't a clear warning.

**Deliberately not fixed** (low impact, larger change; INFERRED):
- a scan can fail if an earlier stopped run of the same stock takes more than 2 minutes to finish its last step;
- a very narrow Stop-versus-verdict race;
- a closed position's USD value uses today's exchange rate (tiny for SAR, which is pegged);
- a resumed run pays again to voice lines it already had;
- a joined run keeps the language of whoever started it.
