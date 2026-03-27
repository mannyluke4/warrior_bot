# DIRECTIVE: Switch from TWS to IB Gateway (Headless)

**Date:** 2026-03-27
**Priority:** P0 — This is blocking every morning session.
**Problem:** TWS via IBC fails to start unattended at 2:00 AM. AppleEvent timeouts, window server issues, and TWS UI dialogs prevent reliable automated startup. Two consecutive mornings lost.

---

## What to Do

### Step 1: Install IB Gateway (if not already installed)

IB Gateway is a separate download from TWS. It's a headless process — no GUI, no AppleScript, no window server dependency.

Download from: https://www.interactivebrokers.com/en/trading/ibgateway-stable.php

Install it on the Mac Mini. It installs alongside TWS — they don't conflict.

### Step 2: Configure IBC for Gateway Mode

IBC supports both TWS and Gateway. The switch is one config change.

Edit `~/ibc/config.ini`:
```ini
# Change this line:
TradingMode=paper

# Make sure this is set:
GatewayOrTws=gateway
```

Edit `~/ibc/gatewaystart.sh` (or create it) — IBC ships with `gatewaystart.sh` alongside `twsstart.sh`:
```bash
# The gateway start script should already exist at:
~/ibc/gatewaystartmacos.sh
# If not, copy from IBC's scripts directory
```

### Step 3: Update daily_run.sh

Replace the TWS startup with Gateway startup:

```bash
# OLD (TWS — broken):
echo "Starting TWS via IBC..."
~/ibc/twsstartmacos.sh &

# NEW (Gateway — headless):
echo "Starting IB Gateway via IBC..."
~/ibc/gatewaystartmacos.sh &
```

### Step 4: Change the Port

IB Gateway uses different default ports than TWS:

| Mode | TWS Port | Gateway Port |
|------|----------|-------------|
| Live | 7496 | 4001 |
| Paper | 7497 | **4002** |

Update the `.env` on Mac Mini:
```
IBKR_PORT=4002
```

Also update `bot_ibkr.py` default:
```python
IBKR_PORT = int(os.getenv("IBKR_PORT", "4002"))  # 4002 = Gateway paper
```

### Step 5: Update the Port-Wait in daily_run.sh

```bash
# Change port from 7497 to 4002 in the wait loop:
IBKR_PORT=4002
echo "Waiting for IB Gateway on port $IBKR_PORT..."
for i in $(seq 1 36); do
    if python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',$IBKR_PORT)); s.close()" 2>/dev/null; then
        echo "Gateway is up on port $IBKR_PORT (after ~$((i*5))s)"
        TWS_READY=1
        break
    fi
    echo "  attempt $i/36: port $IBKR_PORT not ready yet, waiting 5s..."
    sleep 5
done
```

### Step 6: Update the Kill Commands

```bash
# OLD (TWS-specific):
pkill -9 -f "java.*tws" 2>/dev/null || true
pkill -9 -f "java.*Jts" 2>/dev/null || true

# NEW (add Gateway patterns):
pkill -9 -f "java.*tws" 2>/dev/null || true
pkill -9 -f "java.*Jts" 2>/dev/null || true
pkill -9 -f "java.*ibgateway" 2>/dev/null || true
pkill -9 -f "java.*IBGateway" 2>/dev/null || true
```

### Step 7: Test

```bash
# Manual test:
~/ibc/gatewaystartmacos.sh &

# Wait ~60 seconds, then:
python3 -c "
from ib_insync import IB
ib = IB()
ib.connect('127.0.0.1', 4002, clientId=1)
print(f'Connected: {ib.isConnected()}')
print(f'Account: {ib.managedAccounts()}')
ib.disconnect()
"
```

Gateway should connect faster than TWS (no UI to render) — typically 30-60 seconds vs TWS's 90-180 seconds.

### Step 8: Verify API Settings in Gateway

When Gateway first starts, it shows a minimal settings screen. Verify:
- API → Settings → Enable ActiveX and Socket Clients: **checked**
- Socket port: **4002** (paper)
- Read-Only API: **unchecked** (we need to place orders)
- Allow connections from localhost only: **checked** (security)

These settings persist after the first configuration.

---

## What NOT to Change

- `bot_ibkr.py` logic — no changes except the default port
- Scanner, detectors, exit logic — all unchanged
- The bot doesn't care whether it's talking to TWS or Gateway — ib_insync uses the same protocol for both

---

## Expected Result

Gateway starts headless at 2:00 AM with zero AppleScript dependency. No GUI, no window server, no dialog boxes. The port opens in 30-60 seconds. The bot connects and runs.

This is what every production IBKR bot uses. TWS is for humans clicking buttons. Gateway is for bots.
