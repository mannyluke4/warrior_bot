# MEI Watchlist-Bypass Trace — 2026-05-13

**Date:** 2026-05-14
**Author:** CC (forensic agent)
**For:** Cowork — pre-Stage-0 WB persistence work
**Trigger:** WB took +$366 on MEI 2026-05-13 16:06 ET; MEI absent from `2026-05-13_scanner.log`.

---

## A. The mechanism (definitive)

**A previous Claude Code session manually injected MEI (with PTBD, NSTS, VNET) into `~/warrior_bot_v2/session_state/2026-05-13/watchlist.json` via an ad-hoc `python -c` heredoc on 2026-05-13 at 12:32:14 ET.** Evidence is in the session transcript at `/Users/duffy/.claude/projects/-Users-duffy/974f3659-ca6f-4fe9-8b04-660bd22a4eaa.jsonl` (assistant timestamps `2026-05-13T16:30:38Z` proposal → `16:32:14Z` Bash tool call). The injected payload appended four entries with `subscribed_at = 2026-05-13T16:32:14.076702+00:00` — matching the file's mtime exactly (`stat`: `2026-05-13T10:32:14 MDT`). Both downstream pollers picked it up automatically: the Setup A sub-bot's `bot_alpaca_subbot.py:poll_watchlist` (line 2347) reads this file every cycle, and the Setup B engine's `data_engine.py:_watchlist_loop` (line 848) also polls it (SETUP_A_ROOT line 107). Within ~5 seconds the sub-bot logged `📡 Sub-bot: 4 new symbols from main bot's watchlist: ['MEI', 'NSTS', 'PTBD', 'VNET']` and the engine logged `subscribed MEI (snapshot)`. The Setup A MAIN bot (`bot_v3_hybrid.py`) never logged a "Subscribed: MEI" event because it never called `subscribe_symbol()` — the JSON was rewritten under it, not by it.

## B. Timing

| Time (ET)   | Event                                                                                       | Source                                            |
|-------------|---------------------------------------------------------------------------------------------|---------------------------------------------------|
| 02:00:15    | `live_scanner.py` aborts — Databento 402 account_delinquent_invoice                         | `2026-05-13_scanner.log`                          |
| 04:00:09    | Setup A main bot cold-boots, picks up 9 stale symbols from `watchlist.txt` (H#17 bypass)    | `2026-05-13_daily.log:79`                         |
| 10:24:37    | `live_scanner.py` retry — wrote "0 candidates"; `watchlist.txt` unchanged                   | `2026-05-13_scanner.log`                          |
| **12:32:14**| **Claude session adds MEI/NSTS/PTBD/VNET to `session_state/2026-05-13/watchlist.json`**     | session jsonl `974f3659…`, file mtime, JSON value |
| 12:32:18    | Setup B engine picks up MEI via `_watchlist_loop`                                           | `engine.log:28`                                   |
| 12:32:15    | Setup A sub-bot picks up MEI via `poll_watchlist`                                           | `subbot_alpaca.log:14721`                         |
| 14:04:01    | Engine wb_bot logs first MEI `WB_OBSERVE`                                                   | `wb_bot.log:381`                                  |
| 16:06       | WB entry on MEI (sub-bot)                                                                   | `subbot_alpaca.log`                               |

## C. Verdict — manual addition

This was a **deliberate manual injection by a prior Claude session with user approval**, not a code path. The proposal turn in the transcript reads: *"Want me to add these to the bot's watchlist? I can append PTBD, NSTS, MEI, VNET to ~/warrior_bot_v2/session_state/2026-05-13/watchlist.json — both bots have a watchlist-polling thread that picks up new symbols. Going to do it?"* — followed by an executed Bash heredoc that opened the file, appended 4 dicts, and `json.dump`-ed it back. The 12:32 ET write touched only the JSON; it did **not** go through `persist_watchlist()` or `subscribe_symbol()`, which is why no `✅ Subscribed:` line appears in `daily.log` and no caller is visible in any python module.

## D. Other hidden channels that can add symbols outside `live_scanner.py`

| File:line                                  | Channel                                                                 |
|--------------------------------------------|-------------------------------------------------------------------------|
| `bot_v3_hybrid.py:1910 run_scanner`        | In-process IBKR `reqScannerSubscription` (TOP_PERC_GAIN), runs every 5 min — top-5 candidates auto-`subscribe_symbol`. Independent of `live_scanner.py`. |
| `bot_v3_hybrid.py:1962 poll_watchlist`     | Reads `watchlist.txt`; H#17 mtime gate skips stale files on cold start. |
| `bot_v3_hybrid.py:2020 wb_persistence inj` | `wb_persistence.active_persisted_symbols()` injects carryover symbols on each poll cycle. |
| `bot_v3_hybrid.py:4151 subscribe_box_symbol` | Box scanner subscribes top box candidate (gated `WB_BOX_ENABLED=0`).  |
| `bot_alpaca_subbot.py:2347 poll_watchlist` | Mirrors Setup A's `session_state/<date>/watchlist.json` — the channel MEI flowed through. |
| `warrior_bot_v2_engine/data_engine.py:848 _watchlist_loop` | Engine mirrors Setup A's `watchlist.json` over IPC to wb_bot/squeeze_bot. |
| `ibkr_scanner.py:133 reqMktData(snapshot=True)` | Each TOP_PERC_GAIN result gets a snapshot subscription that fires `pendingTickersEvent` → tick_cache writes for symbols not in `active_symbols` (cosmetic, not the MEI path here). |
| Ad-hoc `python -c` / `Edit`-tool writes to `session_state/<date>/watchlist.json` | The actual MEI mechanism. No code-side guard. |

## E. Implications for Stage 0

1. **`session_state/<date>/watchlist.json` is the de-facto inter-process "add a symbol" wire** for Setup A sub-bot and the Setup B engine + wb_bot/squeeze_bot. Any code that writes the file gets fanout. Stage 0's WB-persistence layer should treat this file as the canonical channel — and consider gating writes through `persist_watchlist()` so they show up in `daily.log` audits.
2. The `wb_persistence` injection path (`bot_v3_hybrid.py:2020-2035`) already overlaps with what Stage 0 plans to formalize. Reuse it; do not duplicate.
3. The 12:32 ET incident exposes a **logging gap**: the main bot's `daily.log` does NOT record symbols added via direct JSON write (only via `subscribe_symbol`). If WB persistence will inject via the same channel, add a sentinel log line on file-mtime changes so post-hoc forensics is one-grep.
4. The in-process `run_scanner` + `reqScannerSubscription` is a real, undocumented competing channel — Stage 0 design must decide whether to disable it or keep it as a secondary discovery path.

## F. Reproduction test

```bash
# 1. Note current watchlist size
python3 -c "import json; print(len(json.load(open('/Users/duffy/warrior_bot_v2/session_state/2026-05-14/watchlist.json'))))"

# 2. Inject a harmless ticker (use SPY — bot's filters will reject the trade but the subscription proves the channel)
python3 -c "
import json
from datetime import datetime, timezone
p = '/Users/duffy/warrior_bot_v2/session_state/2026-05-14/watchlist.json'
wl = json.load(open(p))
wl.append({'symbol': 'SPY', 'subscribed_at': datetime.now(timezone.utc).isoformat()})
json.dump(wl, open(p, 'w'), indent=2)
"

# 3. Within ~15s, expect:
#    - Setup A sub-bot log: "📡 Sub-bot: 1 new symbols from main bot's watchlist: ['SPY']" → "✅ Subscribed: SPY"
#    - Setup B engine log:  "[ENGINE] ... subscribed SPY (snapshot)"
tail -F ~/warrior_bot_v2/logs/2026-05-14_subbot_alpaca.log ~/warrior_bot_v2_engine/logs/2026-05-14_engine.log | grep -E "SPY|new symbols"
```

If SPY appears in either log within one poll cycle, the mechanism is confirmed live on 05-14. Remove the entry afterwards.

---

**Bottom line.** MEI was not added by code. It was a manual `python -c` write to `session_state/2026-05-13/watchlist.json` by a prior Claude Code session at 12:32:14 ET on 2026-05-13, picked up downstream by both the sub-bot's `poll_watchlist` and the engine's `_watchlist_loop`. The Stage 0 design should formalize this file as the canonical add-channel and gate all writes through a logged code path.
