# IBKR Gateway — "Multiple Paper Trading users" login failure

**Date:** 2026-05-02
**Author:** CC
**Status:** BLOCKED — cannot start IB Gateway in paper mode
**Goal:** External troubleshooting (Perplexity / IBKR support)

---

## Headline

IB Gateway (via IBC, automated startup) fails immediately at login with:

```
Connection to server failed: The specified user has multiple Paper Trading users
associated with it.

Please log on using one of the Paper Trading users and corresponding password.
```

This dialog appears in IBC's diagnostic log within ~1 second of clicking the "Paper Log In" button. **IBC has no way to dismiss this dialog and pick a paper user — it just hangs waiting for human input.**

---

## Account context

The user owns an IBKR brokerage account with **two live login usernames**:
- `mannyluke4` (original)
- `mannylukewb` (newer, recently approved for paper trading)

A new paper trading user appears to have been provisioned recently — possibly tied to `mannylukewb`. Result: the IBKR server now sees ambiguity when either live username is presented in paper mode, because each one resolves to **multiple** paper users.

Both login usernames were tried. **Both produced the identical "multiple Paper Trading users" error**, suggesting IBKR's response is symmetric — it's not specific to one of the two usernames.

The corresponding live trading account number is `DUQ143444`. Yesterday (2026-05-01) the bot connected fine to this account in paper mode using `mannyluke4`. The breakage happened sometime overnight (possibly during an IBKR maintenance window that ran until 2026-05-02 18:00 ET).

---

## What we tried

### Attempt 1 — `mannyluke4` (original live username)

Original `IbLoginId=mannyluke4` in `~/ibc/config.ini`. Worked fine yesterday. Now produces the "multiple paper users" error.

### Attempt 2 — `mannylukewb` (new live username)

Updated `~/ibc/config.ini`:
```
IbLoginId=mannylukewb
IbPassword=<original_password + '?'>      # password modified per user direction
TradingMode=paper
```

Backup of original config at `~/ibc/config.ini.bak_2026-05-02_pre_credchange`.

Same exact error returned.

### Process state for both attempts

- IBC starts cleanly, banner displays
- IB Gateway main window opens
- "Paper Log In" button is clicked by IBC automation
- Within ~700ms the server returns the "multiple Paper Trading users" dialog
- IBC has no handler for this dialog → process hangs indefinitely until killed
- Port 4002 never opens

---

## Verbatim IBC log excerpt

```
2026-05-02 16:05:57:323 IBC: Starting Gateway
2026-05-02 16:05:58:486 IBC: Getting config dialog
2026-05-02 16:05:58:486 IBC: Getting main window
2026-05-02 16:05:58:971 IBC: detected frame entitled: IBKR Gateway; event=Activated
2026-05-02 16:05:58:974 IBC: Login dialog WINDOW_OPENED: LoginState is LOGGED_OUT
2026-05-02 16:05:58:974 IBC: trading mode from settings: tradingMode=paper
2026-05-02 16:05:58:974 IBC: Setting Trading mode = paper
2026-05-02 16:05:59:072 IBC: Setting user name
2026-05-02 16:05:59:073 IBC: Setting password
2026-05-02 16:05:59:073 IBC: Login attempt: 1
2026-05-02 16:05:59:108 IBC: Click button: Paper Log In
2026-05-02 16:05:59:881 IBC: detected dialog entitled: Gateway; event=Opened
2026-05-02 16:05:59:881 IBC: <html>Connection to server failed: The specified user has
                              multiple Paper Trading users associated with it. <br><br>
                              Please log on using one of the Paper Trading users and
                              corresponding password.</html>
```

(Full diagnostic log is at `~/ibc/logs/ibc-3.23.0_GATEWAY-10.37_Saturday.txt`.)

---

## Environment

- macOS Mac mini (Darwin 25.2.0, Apple Silicon)
- IB Gateway version 10.37
- IBC version 3.23.0
- Configured trading mode: paper (gateway port 4002)
- `~/ibc/config.ini`:
  - `TradingMode=paper`
  - `FIX=no`
  - `ExistingSessionDetectedAction=primary`
  - `AutoRestartTime=` (blank)
  - `ColdRestartTime=` (blank)
  - `ClosedownAt=` (blank)

The Mac was up and running normally, screen-sleep disabled, GUI session active (auto-login `duffy`). Saturday so no cron auto-start fired (`0 2 * * 1-5`).

IBKR was in a maintenance window earlier today until 18:00 ET; we waited until after maintenance ended before retrying. Same error after maintenance.

---

## What we need to know

1. **Is this a known IBKR symptom when a second paper account gets provisioned mid-week?** What's the canonical resolution?
2. **What `IbLoginId` value should be used** when one IBKR live login resolves to multiple paper users? Is there a distinct paper-specific username (e.g. `<live>M` or numeric ID like `DUQ143444`), or does IBKR want the IBC user to set some other field (e.g. `Settings.PaperUserId`, `IbPaperUserId`)?
3. **Does IBC support handling this dialog automatically** — i.e., is there a config setting or `acceptIncomingConnectionAction`-style option that picks a default paper user?
4. **Workaround:** can IBKR's web portal be used to "deactivate" or "merge" the duplicate paper user so only one remains, restoring the previous one-to-one mapping?
5. **Manual confirmation flow:** if the user must select once via GUI, will subsequent IBC starts remember the choice (i.e., is the dialog one-time)?

---

## Reproducer for IBKR support / Perplexity

```bash
# Kill anything alive
pkill -9 -f java
pkill -9 -f "ibcstart|ibcalpha|IBC|gatewaystart"
sleep 30   # let IBKR server-side session clear

# Launch
~/ibc/gatewaystartmacos.sh -inline > /tmp/ibc_test.log 2>&1 &

# Within 5-10 seconds the IBC diagnostic log shows the "multiple Paper Trading users" line
tail -f ~/ibc/logs/ibc-*GATEWAY*.txt
```

---

## Impact

Bot cannot start. No live trading possible. No backtest tick-cache backfill possible (relies on the same gateway). Workflow blocked until IBKR auth resolves.

Two-day's planned weekend backfill of YTD tick data — to validate sim/live parity for the trading strategy — is on hold pending this fix.
