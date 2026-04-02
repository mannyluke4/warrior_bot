#!/usr/bin/env python3
"""Analyze EPL MP Re-Entry trades: losers vs winners patterns."""
import json

with open("backtest_status/v2_epl_mp_state.json") as f:
    data = json.load(f)

trades = data["trades"]

# Group trades by stock-day
from collections import defaultdict
stock_days = defaultdict(list)
for t in trades:
    key = f"{t['symbol']}_{t['date']}"
    stock_days[key].append(t)

print("=" * 100)
print("TRADE SEQUENCE ANALYSIS: All 55 trades grouped by stock-day")
print("=" * 100)

# Categorize by exit reason
EPL_EXITS = {"epl_mp_vwap_loss", "epl_mp_time_exit(5bars)", "epl_mp_stop_hit", "epl_mp_trail_exit"}
SQ_EXITS = {"sq_target_hit", "sq_target_hit_exit_full", "sq_para_trail_exit", "sq_vwap_exit",
            "sq_stop_hit", "sq_max_loss_hit"}

def classify_exit(reason):
    if any(reason.startswith(e.replace("(5bars)", "")) for e in EPL_EXITS):
        return "EPL"
    if reason in SQ_EXITS:
        return "SQ"
    return "AMBIG"  # bearish_engulfing, max_loss_hit, topping_wicky — could be either

total_epl_wins = 0
total_epl_losses = 0
total_epl_win_pnl = 0
total_epl_loss_pnl = 0
epl_losers = []
epl_winners = []

for key in sorted(stock_days.keys()):
    trades_list = stock_days[key]
    symbol = trades_list[0]["symbol"]
    date = trades_list[0]["date"]
    total = sum(t["pnl"] for t in trades_list)

    # Check if any trade hit target (graduation event)
    has_graduation = any("target_hit" in t["reason"] for t in trades_list)

    print(f"\n{'─' * 80}")
    print(f"  {symbol} {date}  |  {len(trades_list)} trades  |  Net: ${total:+,.0f}  |  Graduation: {'YES' if has_graduation else 'NO'}")
    print(f"{'─' * 80}")

    for i, t in enumerate(trades_list):
        cat = classify_exit(t["reason"])
        win = "WIN" if t["pnl"] > 0 else ("FLAT" if t["pnl"] == 0 else "LOSS")
        marker = ""
        if cat == "EPL":
            marker = " ◄── EPL"
            if t["pnl"] > 0:
                total_epl_wins += 1
                total_epl_win_pnl += t["pnl"]
                epl_winners.append(t)
            elif t["pnl"] < 0:
                total_epl_losses += 1
                total_epl_loss_pnl += t["pnl"]
                epl_losers.append(t)

        print(f"    T{i+1}: ${t['pnl']:>+8,}  {t['reason']:<35}  [{cat}]  {win}{marker}")

print(f"\n\n{'=' * 100}")
print("EPL-SPECIFIC TRADE SUMMARY")
print("=" * 100)
print(f"Total EPL trades: {total_epl_wins + total_epl_losses}")
print(f"EPL Wins:   {total_epl_wins} trades, ${total_epl_win_pnl:+,}")
print(f"EPL Losses: {total_epl_losses} trades, ${total_epl_loss_pnl:+,}")
print(f"EPL Net:    ${total_epl_win_pnl + total_epl_loss_pnl:+,}")

print(f"\n\nEPL WINNERS:")
for t in epl_winners:
    print(f"  {t['symbol']} {t['date']}: ${t['pnl']:+,} ({t['reason']})")

print(f"\nEPL LOSERS:")
for t in epl_losers:
    print(f"  {t['symbol']} {t['date']}: ${t['pnl']:+,} ({t['reason']})")

# Analyze trade position in sequence
print(f"\n\n{'=' * 100}")
print("TRADE POSITION ANALYSIS (on 5-trade days)")
print("=" * 100)

for pos in range(1, 6):
    wins = 0
    losses = 0
    win_pnl = 0
    loss_pnl = 0
    for key in sorted(stock_days.keys()):
        tl = stock_days[key]
        if len(tl) >= 5 and len(tl) >= pos:
            t = tl[pos - 1]
            if t["pnl"] > 0:
                wins += 1
                win_pnl += t["pnl"]
            elif t["pnl"] < 0:
                losses += 1
                loss_pnl += t["pnl"]
    total_ct = wins + losses
    wr = wins / total_ct * 100 if total_ct > 0 else 0
    print(f"  Position {pos}: {wins}W/{losses}L ({wr:.0f}% WR), Win P&L=${win_pnl:+,}, Loss P&L=${loss_pnl:+,}, Net=${win_pnl+loss_pnl:+,}")

# Net re-entry P&L per stock-day (after first trade)
print(f"\n\n{'=' * 100}")
print("RE-ENTRY VALUE BY STOCK-DAY (all trades after T1)")
print("=" * 100)

reentry_positive = []
reentry_negative = []

for key in sorted(stock_days.keys()):
    tl = stock_days[key]
    if len(tl) < 2:
        continue
    t1 = tl[0]
    re_entries = tl[1:]
    re_net = sum(t["pnl"] for t in re_entries)
    t1_hit_target = "target_hit" in t1["reason"]
    status = "POSITIVE" if re_net > 0 else "NEGATIVE"

    print(f"  {tl[0]['symbol']} {tl[0]['date']}: T1=${t1['pnl']:+,} ({t1['reason']}) → {len(re_entries)} re-entries net ${re_net:+,} [{status}]")
    if re_net > 0:
        reentry_positive.append((key, t1["pnl"], re_net, len(re_entries)))
    else:
        reentry_negative.append((key, t1["pnl"], re_net, len(re_entries)))

print(f"\n  POSITIVE re-entry days: {len(reentry_positive)}")
for key, t1_pnl, re_net, ct in reentry_positive:
    print(f"    {key}: T1=${t1_pnl:+,} → {ct} re-entries = ${re_net:+,}")
print(f"  NEGATIVE re-entry days: {len(reentry_negative)}")
for key, t1_pnl, re_net, ct in reentry_negative:
    print(f"    {key}: T1=${t1_pnl:+,} → {ct} re-entries = ${re_net:+,}")

# Key question: does T1 P&L size predict re-entry success?
print(f"\n\n{'=' * 100}")
print("T1 P&L SIZE vs RE-ENTRY OUTCOME")
print("=" * 100)
all_reentries = reentry_positive + reentry_negative
all_reentries.sort(key=lambda x: x[1], reverse=True)
for key, t1_pnl, re_net, ct in all_reentries:
    marker = "✓" if re_net > 0 else "✗"
    print(f"  {marker} {key:<25} T1=${t1_pnl:>+8,}  →  Re-entry net=${re_net:>+8,}  ({ct} trades)")
