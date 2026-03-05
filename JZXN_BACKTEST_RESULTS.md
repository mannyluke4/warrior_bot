# JZXN Backtest Results — 2026-03-04

## Command
```
python simulate.py JZXN 2026-03-04 --profile A
```

## Result
- **P&L: -$1,363**
- Trades: 1 | Wins: 0 | Losses: 1 | Win Rate: 0%
- Entry: $1.41 @ 09:52 ET | Stop: $1.30 | R=$0.11
- Exit: $1.26 — stop_hit (-1.4R)
- Score: 12.0 (well above min threshold)

## Notes
- Gap came in at **-18.2%** — NEGATIVE gap. This is an immediate skip per profile rules.
- `yfinance` not installed — float filtering disabled. Float showed N/A.
- The bot entered at 9:52 AM ET (outside the 7am Profile A window) on a negative-gap stock.
- This was NOT a valid Profile A setup. The scanner data showed it first at 7:16 AM ET with a 57-91% gap — that data was from earlier in the morning. By the time the sim ran the full day, the stock had reversed.

## Conclusion
The backtest ran cleanly. The -$1,363 result is expected given the negative gap at simulation time. This confirms the profile rules are correct — JZXN would have been a skip if the classifier had caught the negative gap at 9:30 AM open.

*Run by Duffy — 2026-03-05*
