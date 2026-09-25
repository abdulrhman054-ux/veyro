# Execution Add-on Report (Alpaca)

## What was built
- **Modes Off / Paper / Live** (Settings → Execution). **Off is the default** for new installs.
- **Broker:** the official `alpaca-py` SDK (v0.44.0; `TradingClient`, `MarketOrderRequest`, `LimitOrderRequest`, `get_clock`, `get_asset`, `cancel_orders`, `close_all_positions`), verified by inspecting the installed SDK before coding.
- **Mock broker:** used only in Paper mode when no Paper keys are saved. It's an in-app simulation labelled **MOCK** in the header, tickets, orders and audit rows. It uses real Yahoo quotes; fills, cash and positions are simulated, and it never contacts Alpaca.
- **Order ticket after a verdict:** Leo proposes (Buy/Overweight → buy; Sell/Underweight → sell; Hold → "no order proposed"). The ticket is pre-filled and editable (dollar amount, or shares for sells; market or limit). Tank then checks every limit on screen, one by one, with the actual numbers. The ticket shows the current price with its source and time, the estimated cost, how many orders are left today, whether the market is open, the mode badge and the disclaimer. On confirm, Leo stamps it "معتمد! / Approved!". Pip announces fills with the exact quantity and price.
- **Orders screen:** kill switch, market clock, portfolio (cash, equity, today's P&L, positions with unrealized P&L; "unavailable" when the broker can't be reached), open orders with Cancel, recent orders, the audit log, CSV export and liquidation (behind a typed phrase).
- **History upgrade:** an "Acted?" column, plus the average return versus SPY for acted-on calls compared with ignored ones.

## How each rule is enforced (backend: `backend/veyro/execution/service.py`)
| Rule | Enforcement |
|---|---|
| 1 Alpaca only, official SDK | `AlpacaBroker` wraps `alpaca.trading.client.TradingClient`; nothing else can submit |
| 2 Three modes, Off default | `exec_mode` setting, default `"off"`; `propose()` raises `mode_off` |
| 3 Live unlock | `set_mode("live")` requires validated live keys (`exec_live_keys_valid`), `limits_confirmed:live`, and the exact phrase «أفهم أن هذا مال حقيقي» (or "I understand this is real money" on the English screen). Leaving Live clears `exec_live_unlocked`. A red LIVE badge shows in the header and on every ticket |
| 4 Human confirmation | `propose()` only creates a ticket and a one-time token (5-minute expiry). `confirm(ticket_id, token)` is the **only** caller of `broker.submit` (checked by an AST test). The route also needs the body `confirm: true`. There is no batch or auto confirm, and no scheduler |
| 5 Risk limits on the backend | `_checks()` covers: max per order, per-symbol exposure (position + open buys + this order), daily loss (equity − last_equity), orders per day (from the audit log, NY date), cash-only, and no-short. It runs at **propose and again at confirm**. Defaults are $500 / $1,000 / $200 / 5, editable within bounds |
| 6 Kill switch | `kill()`: cancel all open orders, then mode → Off. Liquidation is a separate call (`liquidate(phrase)`) |
| 7 Order types / no margin, shorting, options, crypto | market/limit only; `us_equity` + tradable only; symbol regex (no option or crypto symbols); DAY, `extended_hours=False`; buys ≤ min(cash, non-marginable buying power); sells ≤ shares held |
| 8 Market status | `broker.clock()`: a closed market refuses market orders with Leo's offer of a limit order for the next open, or cancel. Nothing is queued silently |
| 9 Keys | Keyring entries `alpaca:paper:*` and `alpaca:live:*`; validated against the matching Alpaca environment before saving; only masked values are returned; **never read from .env**; the log filter scrubs `PK…` and header patterns |
| 10 Audit log | `exec_audit` records every proposal, rejection, confirmation, submission, fill, cancellation, failure, kill, liquidation, mode change and limits/keys change. Each row has a timestamp, mode, broker, session (verdict) id, a limits snapshot and the scrubbed broker response. It's shown on the Orders screen and exported via `/api/exec/audit.csv` |
| 11 No live orders by Claude | Tests and verification run with `VEYRO_BLOCK_LIVE=1`, so a live broker can't even be constructed. Live keys were never entered. All order tests used the Mock broker |
| Extra | Mutating `/api/exec/*` routes require the Veyro page's Origin, so a scripted or cross-site POST gets a 403 |

## Verified, and how
- **Unit tests** (`backend/tests/test_execution.py`, 18 passing, Mock broker; re-run after the final changes): full market flow and audit; limit order open then cancel; one-time token; each limit (max order, exposure, orders/day, daily loss) plus re-checking at confirm; no short; refusal of short/stop/crypto/option symbols; closed market; every Live unlock step and re-lock; kill switch; liquidation phrase; CSV; the static "submit only from confirm" check; keys absent from status.
- **Browser (Playwright, `tools/verify_app.py`)**, with screenshots in `verification/execution/`:
  - `e01` Paper without keys → MOCK;
  - `e02`/`e03` market order: ticket, Tank's checks, confirm, stamp, filled;
  - `e04`/`e05` limit order open, then cancelled from the Orders screen;
  - `e06`–`e09` each risk limit blocking the ticket (confirm disabled);
  - server-side rejections checked directly (over-limit ticket gets no token; short / stop / `confirm:false` refused; a scripted POST without Origin gets 403);
  - `e10` kill switch with an open order;
  - `e11` Live unlock disabled without keys/limits, and the backend refusing Live;
  - `e12` audit log and CSV containing every event type;
  - `e13` closed market (English screen): market order refused, limit order offered.
- **Night-time testing note:** fills of Mock market orders were tested with `VEYRO_MOCK_CLOCK_OPEN=1`, which only makes the **Mock** broker act as if the market were open. The closed-market flow was tested against the real market clock.

## Not tested
- **Real Alpaca Paper account:** no Paper keys were available, so every order test used Mock (as the add-on brief allows). `AlpacaBroker` was written against the installed SDK signatures but has **not made a real call**. Before relying on it, save your Paper keys (the save step validates them against Alpaca) and place one small Paper market order and one limit order.
- **Live:** deliberately never exercised. Live keys were never entered, and the live broker is blocked in tests.
- Alpaca order-status streaming isn't used; the app polls every 5 seconds.
- Fractional and notional edge cases on real Alpaca (e.g. non-fractionable assets) are handled in code but only exercised through Mock.

## Risks
- Real-money orders can lose money. Limits reduce but don't remove risk. The defaults are conservative, but the user can raise them.
- Daily P&L uses Alpaca's `equity − last_equity`, which includes unrealized moves (conservative: it blocks earlier).
- The per-symbol exposure check values open limit buys at their limit price and notional orders at their dollar amount, which may differ slightly from final fills.
- If the PC sleeps mid-session, polling pauses, but no orders are placed without confirmation.
