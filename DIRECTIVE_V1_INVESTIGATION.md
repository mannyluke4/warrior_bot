# DIRECTIVE: Investigate V1 Bot April 1 Session

**Date:** April 1, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P1 — Quick investigation, answer tonight if possible

---

## Context

V1 bot ran alongside V2 on April 1. V2 took zero trades (known PRIMED→ARMED gap). V1 took 4 trades via Alpaca — all losers (-$907 total). Two positions became "phantom" — the bot lost awareness and they had to be manually closed on the Alpaca dashboard.

We need to know exactly what strategy V1 was running and why positions went phantom.

---

## Questions to Answer

### Q1: What strategy was active?

Check V1's `.env` file on the Mac Mini:
```bash
cat ~/warrior_bot/.env | grep WB_SQUEEZE
cat ~/warrior_bot/.env | grep WB_MP
cat ~/warrior_bot/.env | grep WB_ROSS
```

Was `WB_SQUEEZE_ENABLED=1`? Was `WB_MP_ENABLED=1`? Were today's trades squeeze entries or micro pullback entries?

### Q2: What do the V1 logs show?

Pull the V1 logs from the Mac Mini:
```bash
ls -la ~/warrior_bot/logs/2026-04-01*
```

For each of the 4 trades (VOR, GVH, APLX, ELAB), find:
- The PRIMED/ARMED/ENTRY log lines (if squeeze) or impulse/pullback/confirm lines (if MP)
- The exit log lines — did the bot attempt to sell?
- Any errors, timeouts, or exceptions between entry and exit
- The exact `setup_type` recorded for each trade

```bash
grep -E "VOR|GVH|APLX|ELAB" ~/warrior_bot/logs/2026-04-01*.log | grep -E "ENTRY|EXIT|FILL|ORDER|ARMED|PRIMED|error|timeout|exception|phantom|position"
```

### Q3: Why did VOR and APLX become phantom positions?

The Alpaca dashboard shows:
- **VOR:** Bought 324 shares at 07:32. Bot did NOT sell. User manually sold at 09:11 (-$303).
- **APLX:** Bought 4,166 shares at 07:34. Bot sold 2,083 at 07:35 but left 2,083 orphaned until 09:14.
- **ELAB:** Bought 2,083 shares at 12:53. Bot never sold. User manually closed at 12:53 (-$130).

For each phantom:
1. Did the bot's log show an exit attempt?
2. Was there an error submitting the sell order?
3. Did the bot crash/restart between entry and exit?
4. Did the fill verification timeout and assume no fill, but the order actually filled?

```bash
# Look for the critical disconnect moment
grep -A5 -B5 "VOR" ~/warrior_bot/logs/2026-04-01*.log | grep -E "sell|exit|order|error|timeout|cancel|fill"
grep -A5 -B5 "APLX.*sell\|APLX.*exit\|APLX.*order" ~/warrior_bot/logs/2026-04-01*.log
```

### Q4: What scanner was V1 using?

Was `WB_ENABLE_DYNAMIC_SCANNER=1` or was it reading from `watchlist.txt`?

```bash
cat ~/warrior_bot/.env | grep SCANNER
cat ~/warrior_bot/watchlist.txt 2>/dev/null
```

If using the Alpaca `MarketScanner`, how did it find VOR, GVH, APLX, and ELAB? What were the scanner criteria?

### Q5: What data feed was V1 on?

```bash
cat ~/warrior_bot/.env | grep DATA_FEED
cat ~/warrior_bot/.env | grep FEED
```

Was it `sip` or `iex`? This matters because IEX data was the root cause of all the V1 scanner divergence issues.

---

## Deliverable

Save answers to: `cowork_reports/2026-04-01_v1_investigation.md`

Include:
1. The exact `.env` settings (strategy flags, scanner mode, data feed)
2. The relevant log excerpts for each phantom position
3. Root cause for the phantom positions (error? timeout? crash?)
4. Whether today's trades were squeeze or MP
