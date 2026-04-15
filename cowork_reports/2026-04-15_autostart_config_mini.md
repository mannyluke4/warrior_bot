# Mac mini auto-start configuration — full inventory for MBP replication

**Author:** CC (Opus)
**Date:** 2026-04-15 evening
**For:** Manny / MBP-Cowork
**Purpose:** Capture every auto-start setting on the Mac mini so it can be emulated (or deliberately *not* emulated) on the MacBook Pro. Assume nothing persists across machines — only the code does.

---

## 1. Crontab

```
0  2 * * 1-5  /bin/bash ~/warrior_bot_v2/daily_run_v3.sh >> ~/warrior_bot_v2/logs/cron_$(date +%Y-%m-%d).log 2>&1
30 2 * * 1-5  /bin/bash ~/warrior_bot_v2/check_bot.sh
```

- `02:00 MT` Mon-Fri: full daily run (wake screen, start Gateway via IBC, start scanner, start bot, watchdog until 18:05 MT).
- `02:30 MT` Mon-Fri: health check. If bot is down, relaunches `daily_run_v3.sh`.

To install on MBP: `crontab -e`, paste the two lines. Both paths are `~/warrior_bot_v2/...` so they work if the repo is cloned to the same relative location.

**Decision for MBP:** probably DON'T install these on MBP if the mini is the authoritative auto-bot. Running two copies competing for the same IBKR account is what caused today's 119 CRITICAL messages. MBP should be manual-only unless/until you shut down the mini.

---

## 2. `~/warrior_bot_v2/daily_run_v3.sh`

The main orchestration script. Key behaviors:

- Sets `set -euo pipefail` — any unexpected error exits.
- `LOG_FILE=~/warrior_bot_v2/logs/${TODAY}_daily.log` via `exec > >(tee -a ...)`.
- Trap on EXIT: kills bot/scanner/gateway-watchdog/caffeinate, commits + pushes logs to `v2-ibkr-migration`.
- Steps:
  1. Wake screen via `caffeinate -u -t 30`
  2. Dismiss lock screen via osascript (key code 53 = Esc)
  3. Type unlock password via osascript (reads `~/.mac_unlock_pw`)
  4. Verify desktop active via `tell application "Finder" to activate`
  5. Start `caffeinate -dims -w $$` to hold machine awake for entire session
  6. `git pull origin v2-ibkr-migration`
  7. `sntp -S time.apple.com` — NTP time sync (non-root; skipped if fails)
  8. Activate venv, run pre-flight Python import check
  9. Kill any stale Gateway/TWS/Java/bot processes
  10. Start IB Gateway via IBC (`~/ibc/gatewaystartmacos.sh -inline`)
  11. Wait up to 360s for port 4002 to open
  12. Start `live_scanner.py` (writes `watchlist.txt`)
  13. Start `bot_v3_hybrid.py`
  14. 15s post-launch health check (kill -0 the PID)
  15. Background Gateway-port watchdog (logs warning if port 4002 drops during session)
  16. Main watchdog loop: sleep until 18:05 MT (= 20:05 ET = 5 min after evening window close)
  17. Kill bot, commit + push logs

**MBP decision:** the whole script is Mac-mini-centric (expects display, keyboard unlock, IBC setup, caffeinate, specific log paths). If you port it to MBP for manual use, you'll want to remove the unlock-password + osascript blocks (MBP is normally logged in + awake).

---

## 3. `~/warrior_bot_v2/check_bot.sh`

Pre-market health check. Lightweight:

- Logs to `~/warrior_bot_v2/logs/healthcheck_<date>.log`.
- `pgrep -f bot_v3_hybrid.py` — if not found, `nohup bash daily_run_v3.sh &`.
- `socket.connect(('127.0.0.1', 4002))` — verifies Gateway is up.

**MBP decision:** skip unless you want MBP auto-restarting on downtime. If running warrior_manual (interactive), the script isn't applicable.

---

## 4. IB Gateway via IBC (Interactive Brokers Controller)

Location on mini: `~/ibc/`

```
commandsend.sh                 IBC command sender
config.ini                     IBC + IBKR credentials (IbLoginId, IbPassword, TradingMode=paper)
enableapi.sh
gatewaystartmacos.sh           entry point used by daily_run_v3.sh
IBC.jar                        IBC binary
LICENSE.txt
local.ibc-gateway.plist        (launchd plist — NOT active on mini's crontab path)
logs/                          IBC's own logs
README.txt
reconnectaccount.sh
```

Key fields in `~/ibc/config.ini`:
- `IbLoginId=<REDACTED>` — live account login
- `IbPassword=<REDACTED>` — stored in config (not keychain)
- `TradingMode=paper` — PAPER, not live
- `OverrideTwsApiPort=` — empty (uses Gateway default 4002 for paper, 4001 for live)
- `ReadOnlyLogin=no`
- `BypassOrderPrecautions=` empty

**MBP decision:**

- If MBP will run its own IB Gateway (independent of mini): needs IBC installed at `~/ibc/`, its own `config.ini` with **paper creds**, and its own port (4002 for paper). If both machines log in with the same IBKR account simultaneously, IBKR error 10197 fires (exactly what happened today).
- If MBP will tunnel to mini's Gateway via Tailscale (per Phase 2 of the `2026-04-12_directive_warrior_manual.md`): skip local IBC on MBP entirely. Tunnel `localhost:4002` on MBP to mini's `:4002`. That avoids the competing-session problem.
- **Recommended default:** tunnel. Running two Gateways is what bit us today.

---

## 5. `~/.mac_unlock_pw`

```
-rw-------  1 duffy  staff  12 Mar 30 16:19 /Users/duffy/.mac_unlock_pw
```

- Permissions: `600` (owner-only readable)
- 12 bytes of content (user's macOS login password, newline-terminated)
- Used by `daily_run_v3.sh` to unlock the mini's desktop after cron wakes it

**MBP decision:** don't replicate unless you want unattended morning wake. If MBP stays logged-in, skip. If you do create one, `chmod 600` is mandatory.

---

## 6. pmset (power management)

```
SleepDisabled     1
sleep             0   (sleep prevented by caffeinate)
disksleep         10
```

Mini has sleep disabled at system level + `caffeinate -dims` during sessions. MASTER_TODO still lists `pmset` config as "NOT APPLIED" but the actual running state on mini shows `SleepDisabled=1`, which was probably applied manually at some point.

**MBP decision:** only if running auto-bot overnight/daily. Manual use doesn't need it. Commands to replicate:
```bash
sudo pmset -a sleep 0 displaysleep 0
sudo pmset -a disksleep 0  # optional; mini has it at 10
```

---

## 7. LaunchAgents / LaunchDaemons

None warrior-related. User `~/Library/LaunchAgents/` has Google Updater + Keystone only. `/Library/LaunchDaemons/` has nothing matching `bot/warrior/ibkr/gateway/ib_`. All auto-start on mini is via **cron**, not launchd.

(Note: `~/ibc/local.ibc-gateway.plist` exists as a template but isn't loaded into launchctl on the mini. Cron drives everything.)

**MBP decision:** if you prefer launchd-based scheduling (survives reboots better than cron in some macOS configs), `launchctl` is an option. Not required.

---

## 8. Accessibility permissions (for osascript keystroke)

`daily_run_v3.sh` types the unlock password via `osascript -e "tell application \"System Events\" to keystroke ..."`. This requires **System Settings → Privacy & Security → Accessibility** to grant the scheduling agent permission:

- The grantee is typically `bash` (or `/bin/bash`), `osascript`, `cron`, or `/usr/sbin/cron` depending on macOS version.
- Symptom if missing: `WARN: keystroke failed — check Accessibility permissions` in log.

**MBP decision:** same as `.mac_unlock_pw` — only needed for auto-unlock. Skip if MBP stays logged in.

---

## 9. What's NOT in auto-start (but IS in live config)

These live in `.env` and affect runtime behavior. They're **per-machine** and do NOT cross via git:

- `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` — Alpaca paper keys
- `APCA_PAPER=true`
- `WB_*` feature flags (session resume, squeeze tuning, winsorize, entry retry, etc.)
- Scanner filters (`WB_MIN_GAP_PCT`, `WB_MAX_FLOAT`, etc.)
- Databento subscription / credentials if `live_scanner.py` uses them

**MBP decision:** create `.env` from `.env.example` + fill in MBP-specific values. Any flags you want to keep OFF should stay OFF (e.g., the newly-shipped `WB_SQ_DYNAMIC_ATTEMPTS_ENABLED=0` default stays 0 on MBP too).

---

## 10. IBKR clientId collision — the real gotcha

`bot_v3_hybrid.py` connects to IBKR Gateway with a specific `clientId`. If MBP runs anything that connects to the same Gateway (or same account on a different Gateway) with the same `clientId`, one will kick the other off.

To find current clientId on mini:

```bash
grep -nE "ib\.connect|clientId=" ~/warrior_bot_v2/bot_v3_hybrid.py ~/warrior_manual/manual_trader.py
```

Whatever numbers appear there must be **different** between mini-bot and MBP-manual if both run simultaneously. Best practice:

- `bot_v3_hybrid.py` (mini, auto-trading) → clientId 1
- `live_scanner.py` (mini) → clientId 2
- `warrior_manual` (MBP) → clientId 10 (or any unused int)
- Anything else → 11, 12, ...

Today's tick-drought flood was probably caused by MBP opening a competing Gateway with the same account AND clientId, not a clientId collision specifically — but both are failure modes to avoid.

---

## Recommended MBP posture (my read)

1. **Don't install the crontab on MBP.** The mini is authoritative for auto-trading. MBP is the human-in-the-loop side via warrior_manual.
2. **Don't install IBC locally on MBP.** Instead, Tailscale-tunnel `localhost:4002` to the mini's port. This both avoids the competing-session problem and gives MBP access to the mini's continuous Gateway session.
3. **Create `.env` per-machine** from `.env.example`.
4. **Set a distinct clientId** in `warrior_manual`'s IBKR connect if it's not already parameterized via env var.
5. **Skip pmset / `.mac_unlock_pw` / Accessibility** — MBP is interactive.

If you actually want MBP to run its own independent auto-bot (unusual), then replicate items 1, 2, 4-8 above and use a **different paper account** for MBP to avoid collisions. Same account across two machines with simultaneous Gateway sessions = IBKR error 10197 every time.

---

## Quick replication checklist for MBP

```
[ ] Decide: MBP runs its own auto-bot? Or manual-only via tunnel?
[ ] If manual-only via tunnel:
    [ ] Set up Tailscale (or equivalent) to mini
    [ ] Verify `nc -zv <mini-tailscale-name> 4002` works
    [ ] In warrior_manual .env, point to mini's Gateway host:port
    [ ] Pick unique clientId (e.g., 10)
[ ] If independent auto-bot:
    [ ] Use a SEPARATE IBKR paper account — do not collide with mini
    [ ] Install IBC at ~/ibc/
    [ ] Install the cron jobs
    [ ] Install Accessibility permissions + ~/.mac_unlock_pw (if mini-style unattended)
    [ ] Apply pmset
[ ] Create ~/warrior_bot_v2/.env and ~/warrior_manual/.env from templates
[ ] Verify Python 3.12+ available; recreate venvs on MBP (machine-specific wheels)
[ ] Run health check: `python3 -c "from ib_insync import IB; print('OK')"` in each venv
```

---

*CC (Opus). Every knob on the mini. MBP chooses which to copy.*
