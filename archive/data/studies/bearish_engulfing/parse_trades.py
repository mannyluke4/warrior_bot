#!/usr/bin/env python3
"""Parse verbose backtest outputs and generate Phase 1 + Phase 2 reports."""
import os, re, sys
from pathlib import Path

RAW_DIR = Path(__file__).parent / "raw"

# Stock metadata from directive
STOCKS = [
    ("ROLR", "2026-01-06", 3.6, -6.2),
    ("ACON", "2026-01-08", 0.7, 6.9),
    ("APVO", "2026-01-09", 0.9, -3.4),
    ("BDSX", "2026-01-12", 3.7, 2.7),
    ("PMAX", "2026-01-13", 1.2, -7.4),
    ("ROLR", "2026-01-14", 3.6, -6.2),
    ("BNAI", "2026-01-16", 3.3, -1.8),
    ("GWAV", "2026-01-16", 0.8, -1.4),
    ("LCFY", "2026-01-16", 1.4, -0.6),
    ("ROLR", "2026-01-16", 3.6, -6.2),
    ("SHPH", "2026-01-16", 1.6, -4.0),
    ("TNMG", "2026-01-16", 1.2, -0.7),
    ("VERO", "2026-01-16", 1.6, -9.1),
    ("PAVM", "2026-01-21", 0.7, -0.2),
    ("MOVE", "2026-01-23", 0.6, 13.6),
    ("SLE",  "2026-01-23", 0.7, 1.5),
    ("BCTX", "2026-01-27", 1.7, 6.7),
    ("HIND", "2026-01-27", 1.5, -0.6),
    ("MOVE", "2026-01-27", 0.6, 13.6),
    ("SXTP", "2026-01-27", 0.9, -4.8),
    ("BNAI", "2026-01-28", 3.3, -1.8),
    ("BNAI", "2026-02-05", 3.3, 0.1),
    ("MNTS", "2026-02-06", 1.3, -7.3),
    ("ACON", "2026-02-13", 0.7, 6.9),
    ("MLEC", "2026-02-13", 0.7, -21.7),
    ("SNSE", "2026-02-18", 0.7, -2.3),
    ("ENVB", "2026-02-19", 0.5, -6.8),
]

def parse_file(sym, date):
    fname = RAW_DIR / f"{sym}_{date}.txt"
    txt = fname.read_text()

    # Parse trade table
    trades = []
    # Match trade rows:   1   07:03   3.5200   3.3500  0.1700   12.0   3.5500  bearish_engulfing_exit_full      +176    +0.2R
    trade_pat = re.compile(
        r'^\s+(\d+)\s+'        # trade num
        r'(\d\d:\d\d)\s+'      # entry time
        r'([\d.]+)\s+'         # entry price
        r'([\d.]+)\s+'         # stop price
        r'([\d.]+)\s+'         # R
        r'([\d.]+)\s+'         # score
        r'([\d.]+)\s+'         # exit price
        r'(\S+)\s+'            # reason
        r'([+\-]?\d+)\s+'      # P&L
        r'([+\-]?[\d.]+)R',    # R-mult
        re.MULTILINE
    )
    for m in trade_pat.finditer(txt):
        trades.append({
            'num': int(m.group(1)),
            'entry_time': m.group(2),
            'entry_price': float(m.group(3)),
            'stop': float(m.group(4)),
            'r': float(m.group(5)),
            'score': float(m.group(6)),
            'exit_price': float(m.group(7)),
            'reason': m.group(8),
            'pnl': int(m.group(9)),
            'r_mult': float(m.group(10)),
        })

    # Parse entry/exit timestamps from verbose log lines
    events = []
    event_pat = re.compile(r'\[(\d\d:\d\d)\] (ENTRY|BEARISH_ENGULFING_EXIT|TOPPING_WICKY_EXIT|stop_hit|trail_stop|tp_hit)')
    for m in event_pat.finditer(txt):
        events.append((m.group(1), m.group(2)))

    # Match exits to trades
    entry_idx = 0
    for t in trades:
        # Find the entry event
        while entry_idx < len(events) and events[entry_idx][1] != 'ENTRY':
            entry_idx += 1
        if entry_idx < len(events):
            # Next non-ENTRY event after this entry is the exit
            exit_idx = entry_idx + 1
            while exit_idx < len(events) and events[exit_idx][1] == 'ENTRY':
                exit_idx += 1
            if exit_idx < len(events):
                t['exit_time'] = events[exit_idx][0]
            else:
                # Must have been a stop or trail from the summary (no verbose line)
                t['exit_time'] = '??:??'
            entry_idx = exit_idx + 1

        # Calculate time held (approximate - minute resolution)
        if t.get('exit_time') and t['exit_time'] != '??:??':
            eh, em = map(int, t['entry_time'].split(':'))
            xh, xm = map(int, t['exit_time'].split(':'))
            t['minutes_held'] = (xh * 60 + xm) - (eh * 60 + em)
        else:
            t['minutes_held'] = None

    return trades

def main():
    all_sessions = []
    for sym, date, flt, gap in STOCKS:
        trades = parse_file(sym, date)
        session_pnl = sum(t['pnl'] for t in trades)
        all_sessions.append({
            'sym': sym, 'date': date, 'float': flt, 'gap': gap,
            'trades': trades, 'session_pnl': session_pnl,
        })

    # === PHASE 1: Raw trade data ===
    p1 = []
    p1.append("# Phase 1: Verbose Per-Trade Data — 27 Profile A Sessions\n")
    p1.append(f"Generated from backtest runs on 2026-03-05\n")
    p1.append(f"Command: `python simulate.py SYMBOL DATE 07:00 12:00 --profile A --ticks --no-fundamentals -v`\n\n")

    total_trades = 0
    total_pnl = 0
    for s in all_sessions:
        total_trades += len(s['trades'])
        total_pnl += s['session_pnl']
        p1.append(f"## {s['sym']} — {s['date']} (Float {s['float']}M, Gap {s['gap']}%)\n")
        p1.append(f"| # | Entry Time | Entry | Stop | R | Score | Exit Time | Exit | Reason | P&L | R-Mult | Min Held |")
        p1.append(f"|---|------------|-------|------|---|-------|-----------|------|--------|-----|--------|----------|")
        for t in s['trades']:
            et = t.get('exit_time', '??')
            mh = t.get('minutes_held')
            mh_str = f"{mh}m" if mh is not None else "?"
            p1.append(f"| {t['num']} | {t['entry_time']} | {t['entry_price']:.4f} | {t['stop']:.4f} | {t['r']:.4f} | {t['score']} | {et} | {t['exit_price']:.4f} | {t['reason']} | ${t['pnl']:+,} | {t['r_mult']:+.1f}R | {mh_str} |")
        p1.append(f"\n**Session P&L: ${s['session_pnl']:+,}** ({len(s['trades'])} trades)\n")

    p1.append(f"\n---\n## Summary\n- **Total sessions:** {len(all_sessions)}")
    p1.append(f"- **Total trades:** {total_trades}")
    p1.append(f"- **Total P&L:** ${total_pnl:+,}")

    Path(__file__).parent.joinpath("phase1_verbose_trades.md").write_text("\n".join(p1))
    print(f"Phase 1 written: {total_trades} trades, ${total_pnl:+,} total P&L")

    # === PHASE 2: Trade 1 Analysis ===
    p2 = []
    p2.append("# Phase 2: Trade 1 Exit Analysis\n")

    # Q1: How many Trade 1 exits were BE?
    trade1s = [(s, s['trades'][0]) for s in all_sessions if s['trades']]
    be_t1 = [(s, t) for s, t in trade1s if 'bearish_engulfing' in t['reason']]
    other_t1 = [(s, t) for s, t in trade1s if 'bearish_engulfing' not in t['reason']]

    p2.append(f"## Q1: How many Trade 1 exits were bearish engulfing?\n")
    p2.append(f"- **Bearish engulfing:** {len(be_t1)} / {len(trade1s)} ({100*len(be_t1)/len(trade1s):.0f}%)")
    p2.append(f"- **Other exits:** {len(other_t1)} / {len(trade1s)} ({100*len(other_t1)/len(trade1s):.0f}%)\n")

    p2.append("### BE Trade 1 exits:\n")
    p2.append("| # | Symbol | Date | Entry | Exit | P&L | R-Mult | Min Held |")
    p2.append("|---|--------|------|-------|------|-----|--------|----------|")
    for i, (s, t) in enumerate(be_t1, 1):
        mh = t.get('minutes_held')
        mh_str = f"{mh}m" if mh is not None else "?"
        p2.append(f"| {i} | {s['sym']} | {s['date']} | {t['entry_price']:.2f} | {t['exit_price']:.2f} | ${t['pnl']:+,} | {t['r_mult']:+.1f}R | {mh_str} |")

    p2.append("\n### Non-BE Trade 1 exits:\n")
    p2.append("| # | Symbol | Date | Entry | Exit | Reason | P&L | R-Mult | Min Held |")
    p2.append("|---|--------|------|-------|------|--------|-----|--------|----------|")
    for i, (s, t) in enumerate(other_t1, 1):
        mh = t.get('minutes_held')
        mh_str = f"{mh}m" if mh is not None else "?"
        p2.append(f"| {i} | {s['sym']} | {s['date']} | {t['entry_price']:.2f} | {t['exit_price']:.2f} | {t['reason']} | ${t['pnl']:+,} | {t['r_mult']:+.1f}R | {mh_str} |")

    # Q2: Trade 1 P&L comparison
    p2.append(f"\n## Q2: Trade 1 P&L — BE vs Other\n")
    be_pnl = sum(t['pnl'] for _, t in be_t1)
    other_pnl = sum(t['pnl'] for _, t in other_t1)
    be_wins = sum(1 for _, t in be_t1 if t['pnl'] > 0)
    other_wins = sum(1 for _, t in other_t1 if t['pnl'] > 0)

    p2.append(f"| Metric | BE Trade 1 | Non-BE Trade 1 |")
    p2.append(f"|--------|-----------|---------------|")
    p2.append(f"| Count | {len(be_t1)} | {len(other_t1)} |")
    p2.append(f"| Total P&L | ${be_pnl:+,} | ${other_pnl:+,} |")
    p2.append(f"| Avg P&L | ${be_pnl/len(be_t1):+,.0f} | ${other_pnl/len(other_t1):+,.0f} |")
    p2.append(f"| Win Rate | {100*be_wins/len(be_t1):.0f}% ({be_wins}/{len(be_t1)}) | {100*other_wins/len(other_t1):.0f}% ({other_wins}/{len(other_t1)}) |")

    be_rmults = [t['r_mult'] for _, t in be_t1]
    other_rmults = [t['r_mult'] for _, t in other_t1]
    p2.append(f"| Avg R-Multiple | {sum(be_rmults)/len(be_rmults):+.2f}R | {sum(other_rmults)/len(other_rmults):+.2f}R |")

    # Q3: How fast did Trade 1 BE exits happen?
    p2.append(f"\n## Q3: Trade 1 BE Exit Speed\n")
    be_times = [(s, t, t.get('minutes_held', 999)) for s, t in be_t1]

    lt2 = [(s, t) for s, t, m in be_times if m is not None and m < 2]
    t2_5 = [(s, t) for s, t, m in be_times if m is not None and 2 <= m < 5]
    t5_10 = [(s, t) for s, t, m in be_times if m is not None and 5 <= m < 10]
    gt10 = [(s, t) for s, t, m in be_times if m is not None and m >= 10]

    p2.append(f"| Time Bucket | Count | Sessions | Avg P&L |")
    p2.append(f"|-------------|-------|----------|---------|")
    for label, group in [("< 2 min", lt2), ("2-5 min", t2_5), ("5-10 min", t5_10), ("> 10 min", gt10)]:
        if group:
            names = ", ".join(f"{s['sym']}({s['date'][-5:]})" for s, t in group)
            avg = sum(t['pnl'] for _, t in group) / len(group)
            p2.append(f"| {label} | {len(group)} | {names} | ${avg:+,.0f} |")
        else:
            p2.append(f"| {label} | 0 | — | — |")

    # Q4: Stocks where Trade 1 BE < 5 min — what happened next?
    fast_be = [(s, t) for s, t, m in be_times if m is not None and m < 5]
    p2.append(f"\n## Q4: Trade 1 BE exits < 5 minutes — what happened next?\n")
    p2.append(f"Found **{len(fast_be)}** sessions where Trade 1 exited via BE in < 5 minutes.\n")

    for s, t1 in fast_be:
        p2.append(f"### {s['sym']} — {s['date']}")
        p2.append(f"- **Trade 1:** Entry {t1['entry_time']} @ {t1['entry_price']:.2f}, Exit @ {t1['exit_price']:.2f}, P&L ${t1['pnl']:+,} ({t1['r_mult']:+.1f}R), held {t1.get('minutes_held', '?')}m")

        remaining = s['trades'][1:]
        if remaining:
            p2.append(f"- **Re-entries:** {len(remaining)} more trades")
            for rt in remaining:
                p2.append(f"  - Trade {rt['num']}: Entry {rt['entry_time']} @ {rt['entry_price']:.2f}, Exit @ {rt['exit_price']:.2f}, {rt['reason']}, P&L ${rt['pnl']:+,} ({rt['r_mult']:+.1f}R)")
        else:
            p2.append(f"- **Re-entries:** None")

        p2.append(f"- **Session total:** ${s['session_pnl']:+,}")

        # Did price exceed exit price later? Check from remaining trades
        best_later = max([rt['exit_price'] for rt in remaining] + [rt['entry_price'] for rt in remaining]) if remaining else t1['exit_price']
        if best_later > t1['exit_price']:
            p2.append(f"- **Price exceeded BE exit?** YES — later trades touched {best_later:.2f} (BE exit was {t1['exit_price']:.2f})")
        else:
            p2.append(f"- **Price exceeded BE exit?** Unknown (no later trades or prices below)")
        p2.append("")

    # Summary stats for Q4
    fast_be_session_pnls = [s['session_pnl'] for s, _ in fast_be]
    fast_be_t1_pnls = [t['pnl'] for _, t in fast_be]
    p2.append(f"### Q4 Summary")
    p2.append(f"- Sessions with Trade 1 BE < 5m: **{len(fast_be)}**")
    p2.append(f"- Trade 1 total P&L in these sessions: **${sum(fast_be_t1_pnls):+,}**")
    p2.append(f"- Full session total P&L for these sessions: **${sum(fast_be_session_pnls):+,}**")
    p2.append(f"- Sessions where later trades recovered: {sum(1 for s, _ in fast_be if s['session_pnl'] > 0)}/{len(fast_be)}")

    Path(__file__).parent.joinpath("phase2_analysis.md").write_text("\n".join(p2))
    print(f"Phase 2 written: {len(be_t1)} BE Trade 1 exits out of {len(trade1s)}")
    print(f"  BE T1 total: ${be_pnl:+,}, Other T1 total: ${other_pnl:+,}")
    print(f"  Fast BE (<5m): {len(fast_be)} sessions")

if __name__ == '__main__':
    main()
