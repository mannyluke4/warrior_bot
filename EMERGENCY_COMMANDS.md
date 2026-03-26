# Emergency Commands — Run from Phone via SSH

SSH in: `ssh duffy@<mac-mini-ip>`

---

## Check Bot Status
```bash
ps aux | grep bot_ibkr | grep -v grep
```

## Check Today's Log
```bash
tail -20 ~/warrior_bot_v2/logs/$(date +%Y-%m-%d)_daily.log
```

## Full Restart (kill everything, start fresh)
```bash
# 1. Kill everything
pkill -f bot_ibkr.py; pkill -f "java.*tws"; pkill -f "java.*Jts"; sleep 5

# 2. Start TWS
~/ibc/twsstartmacos.sh &

# 3. Wait 90 seconds for TWS to login
sleep 90

# 4. Verify TWS is up
python3 -c "import socket; s=socket.socket(); s.settimeout(2); s.connect(('127.0.0.1',7497)); s.close(); print('TWS OK')"

# 5. Start bot
cd ~/warrior_bot_v2 && source venv/bin/activate
python3 -u bot_ibkr.py >> logs/$(date +%Y-%m-%d)_daily.log 2>&1 &
echo "Bot started: PID $!"

# 6. Verify bot is running
sleep 15 && tail -5 logs/$(date +%Y-%m-%d)_daily.log
```

## Quick Start (TWS already running)
```bash
cd ~/warrior_bot_v2 && source venv/bin/activate
pkill -f bot_ibkr.py; sleep 2
python3 -u bot_ibkr.py >> logs/$(date +%Y-%m-%d)_daily.log 2>&1 &
sleep 15 && tail -10 logs/$(date +%Y-%m-%d)_daily.log
```

## Check if TWS is Running
```bash
lsof -i -P | grep java | grep LISTEN
```

## Kill Bot Only (keep TWS)
```bash
pkill -f bot_ibkr.py
```

## Kill Everything
```bash
pkill -f bot_ibkr.py; pkill -f "java.*tws"; pkill -f "java.*Jts"
```
