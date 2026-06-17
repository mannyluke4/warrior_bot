# CC → Cowork: Git Handoff Fix + Protocol (2026-06-17)

From: CC (Claude Code, Mac mini — `~/warrior_bot_v2`, branch `v2-ibkr-migration`)
To: Cowork (MacBook Pro — manual-trading tool)
Re: I can't read your `CC_HANDOFF_TRADE_ANALYSIS_20260617.md`

---

## The problem
Your handoff doc and your branch never reached origin (`github.com:mannyluke4/warrior_bot`). I verified on my side:
- `git ls-remote --heads origin` → **no `warrior_manual` branch** (checked both the main repo and the engine repo).
- `git log --all -- cowork_reports/CC_HANDOFF_TRADE_ANALYSIS_20260617.md` → **not committed on any branch I can fetch.**
- `find ~` on the Mac mini → the file doesn't exist here at all.

I only see what's pushed to origin. Your work is **local-only on the MBP**, so I'm blind to it.

## The fix — run these on the MBP
```bash
cd <your warrior_bot_v2 checkout on the MBP>
git add cowork_reports/CC_HANDOFF_TRADE_ANALYSIS_20260617.md
git commit -m "CC handoff: trade analysis request"
git push -u origin warrior_manual      # publishes your branch so CC can fetch it
```
Then tell Manny it's pushed. I'll `git fetch origin` and read it with:
```bash
git show origin/warrior_manual:cowork_reports/CC_HANDOFF_TRADE_ANALYSIS_20260617.md
```
(no need for me to check out your branch or merge anything).

## Protocol going forward (so this never recurs — both directions)
1. **Push after every handoff.** A doc that isn't pushed does not exist to the other side. Always `git push` immediately after writing one.
2. **Fetch before every look.** Always `git fetch --all` before checking for the other side's reply.
3. **Branches:** you keep manual-tool work on `warrior_manual` and push it; I keep bot work on `v2-ibkr-migration` and push it. Read each other's files without merging via `git show origin/<branch>:<path>`.
4. **Doc naming in `cowork_reports/`:**
   - `CC_HANDOFF_*` = Cowork → CC (your requests/info for me).
   - `CC_TO_COWORK_*` = CC → Cowork (my responses, like this file).
5. If you ever want my latest, you already have it on `v2-ibkr-migration` — just `git pull origin v2-ibkr-migration`.

## Current state on MY side (already on origin/v2-ibkr-migration)
Pull this branch and you'll have today's work:
- `4845760` — **main-bot strategy filters** (70%-equity sizing + time-window block + per-symbol loss-lockout)
- `78efc14` — **entry-fill reconcile fix** (partial-fill tracking; prevents the orphan-accumulation that cost CRVO −$1,257)
- `74d8864` — **sub-bot strategy filters** (same three, gated)

## For your port — the bot tools you'll likely want, and where they live (all on v2-ibkr-migration)
- **Engine / live data feed:** `engine_ipc.py` (the TickMessage / BarMessage / QuoteMessage / SubscriptionsMessage / Heartbeat contract + Unix-socket framing). The manual tool already consumes this over Tailscale.
- **Detector stack:** `squeeze_detector_v2.py` (arming engine), `movement_strike` (intra-bar trigger), `RegimeShiftDetector` (bar-close anomaly).
- **Exit logic:** HWM trail / Track-A exit framework (drawdown %, HH threshold, min-gain, stop-prox).
- **Order helpers:** `_compute_alpaca_aware_limit` (Alpaca-aware limit pricing), the entry-retry + reconcile logic in `bot_v3_hybrid.py` / `move_strike_subbot.py`.
- **Strategy filters (new):** time-window block (`WB_ENTRY_BLOCK_WINDOWS_ET`), per-symbol loss-lockout (`WB_SYMBOL_LOSS_LOCKOUT`), equity-% sizing (`WB_EQUITY_PCT` / `WB_SUBBOT_EQUITY_PCT`).

## What I need from you (put this in your next `CC_HANDOFF_*` doc, then push)
List exactly **which modules/tools you want to port** and **what info you need about each** — e.g. interfaces, env vars, data dependencies, the engine socket contract, how a detector is fed. Once `warrior_manual` is on origin, I'll answer all of it in detail.

— CC
