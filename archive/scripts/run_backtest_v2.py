#!/usr/bin/env python3
"""
Giant Backtest V2 — With Protective Filters

Orchestrator that reads scanner JSONs, applies protective filters,
and runs simulate.py for each candidate with session-level kill switch.

Filters:
- Profile B float ceiling: 10M (was 50M)
- PM volume minimum: 1,000 shares
- Session kill switch: -$2K max loss, 50% give-back, 3 consecutive losses
- Cold market gate: quality A-candidate + 30% gapper required
"""

import json
import os
import re
import subprocess
import sys

from session_manager import SessionManager

ALL_DATES = [
    "2026-01-02", "2026-01-03", "2026-01-05", "2026-01-06", "2026-01-07",
    "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14",
    "2026-01-15", "2026-01-16", "2026-01-21", "2026-01-22", "2026-01-23",
    "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29",
    "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
    "2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13",
    "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23",
    "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27",
]

MIN_PM_VOLUME = 1000


def parse_pnl_from_output(output: str) -> float:
    """Extract gross P&L from simulate.py output."""
    match = re.search(r'Gross P&L:\s*\$([+-]?[\d,]+)', output)
    if match:
        return float(match.group(1).replace(',', ''))
    return 0.0


def is_cold_market(candidates: list[dict]) -> tuple[bool, str]:
    """Check if market is too cold to trade."""
    a_candidates = [c for c in candidates if c.get('profile') == 'A']
    quality_a = [c for c in a_candidates
                 if c['gap_pct'] >= 20 and c.get('pm_volume', 0) >= 5000]
    big_gappers = [c for c in candidates if c['gap_pct'] >= 30]

    if not quality_a:
        return True, "No A-profile candidate with gap>=20% AND pm_vol>=5K"
    if not big_gappers:
        return True, "No candidate with gap>=30%"
    return False, ""


def process_date(date: str, stats: dict):
    """Process a single date: filter candidates and run simulations."""
    json_path = f"scanner_results/{date}.json"
    if not os.path.exists(json_path):
        print(f"  SKIP — no scanner results")
        return

    with open(json_path) as f:
        candidates = json.load(f)

    # ─── COLD MARKET GATE ───
    cold, cold_reason = is_cold_market(candidates)
    if cold:
        print(f"  COLD MARKET SKIP [{date}]: {cold_reason}")
        stats['cold_market_days'] += 1
        # Log what would have been traded
        would_trade = []
        for c in candidates:
            p = c.get('profile', 'X')
            flt = c.get('float_millions')
            gap = c['gap_pct']
            price = c['pm_price']
            pmv = c.get('pm_volume', 0)
            if flt is None or p == 'X':
                continue
            if p == 'A' and 0.5 <= flt <= 5.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 40.0 and pmv >= MIN_PM_VOLUME:
                would_trade.append(f"{c['symbol']}:A")
            elif p == 'B' and 5.0 <= flt <= 10.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 25.0 and pmv >= MIN_PM_VOLUME:
                would_trade.append(f"{c['symbol']}:B")
        if would_trade:
            print(f"  Would-have-traded: {', '.join(would_trade)} ({len(would_trade)} candidates skipped)")
        return

    # ─── FILTER CANDIDATES ───
    profile_a = []
    profile_b = []
    filtered_pm_vol = []
    filtered_float = []

    for c in candidates:
        p = c.get('profile', 'X')
        flt = c.get('float_millions')
        gap = c['gap_pct']
        price = c['pm_price']
        pmv = c.get('pm_volume', 0)

        if flt is None or p == 'X':
            continue

        # PM Volume gate
        if pmv < MIN_PM_VOLUME:
            filtered_pm_vol.append(f"{c['symbol']} (pm_vol={pmv})")
            stats['pm_vol_filtered'] += 1
            continue

        # Profile A: micro-float runner
        if p == 'A' and 0.5 <= flt <= 5.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 40.0:
            profile_a.append(c)
        # Profile B: mid-float (ceiling at 10M)
        elif p == 'B' and 5.0 <= flt <= 10.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 25.0:
            profile_b.append(c)
        elif p == 'B' and flt > 10.0:
            filtered_float.append(f"{c['symbol']} (float={flt}M)")
            stats['float_filtered'] += 1

    # Sort A by gap% desc, B by gap% desc (top 2 only)
    profile_a.sort(key=lambda x: x['gap_pct'], reverse=True)
    profile_b.sort(key=lambda x: x['gap_pct'], reverse=True)
    profile_b = profile_b[:2]

    if filtered_pm_vol:
        print(f"  PM Volume filtered: {', '.join(filtered_pm_vol)}")
    if filtered_float:
        print(f"  Float >10M filtered: {', '.join(filtered_float)}")

    all_candidates = profile_a + profile_b

    if not all_candidates:
        print(f"  No candidates passed filters for {date}")
        return

    # ─── SESSION MANAGER (KILL SWITCH) ───
    session = SessionManager()

    for c in all_candidates:
        sym = c['symbol']
        profile = c['profile']
        sim_start = c.get('sim_start', '07:00')

        # Check kill switch BEFORE running sim
        if session.should_stop():
            idx = all_candidates.index(c)
            remaining = [x['symbol'] for x in all_candidates[idx:]]
            print(f"  KILL SWITCH [{date}]: {session.stop_reason}")
            print(f"  Skipping: {', '.join(remaining)}")
            stats['kill_switch_days'] += 1
            break

        outfile = f"scanner_results/{date}_{sym}.txt"

        # Resume-safe: skip if already exists and has content
        if os.path.exists(outfile) and os.path.getsize(outfile) > 0:
            with open(outfile) as f:
                existing = f.read()
            pnl = parse_pnl_from_output(existing)
            session.record_sim(sym, pnl)
            print(f"  CACHED {sym} (P&L: ${pnl:+,.0f})")
            stats['total_pnl'] += pnl
            stats['total_sims'] += 1
            if pnl > 0:
                stats['winners'] += 1
            elif pnl < 0:
                stats['losers'] += 1
            stats['day_pnl'][date] = stats['day_pnl'].get(date, 0) + pnl
            stats['sim_details'].append((date, sym, profile, pnl))
            continue

        print(f"  RUN  {sym} profile={profile} start={sim_start}")

        # Build simulate.py command
        if profile == "B":
            cmd = f"timeout 180 python simulate.py {sym} {date} {sim_start} 12:00 --profile B --ticks --feed databento --l2 --no-fundamentals"
        else:
            cmd = f"timeout 120 python simulate.py {sym} {date} {sim_start} 12:00 --profile A --ticks --no-fundamentals"

        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=200)
            output = result.stdout + result.stderr

            # Profile B Databento fallback
            if profile == "B" and (result.returncode != 0 or "license_not_found" in output or "403" in output or "Error" in output):
                print(f"  WARN {sym} Databento failed, falling back to Alpaca")
                cmd = f"timeout 120 python simulate.py {sym} {date} {sim_start} 12:00 --profile B --ticks --no-fundamentals"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=140)
                output = result.stdout + result.stderr

            # Write output
            with open(outfile, 'w') as f:
                f.write(output)

            # Parse P&L
            pnl = parse_pnl_from_output(output)
            session.record_sim(sym, pnl)

            stats['total_pnl'] += pnl
            stats['total_sims'] += 1
            if pnl > 0:
                stats['winners'] += 1
            elif pnl < 0:
                stats['losers'] += 1
            stats['day_pnl'][date] = stats['day_pnl'].get(date, 0) + pnl
            stats['sim_details'].append((date, sym, profile, pnl))

            if result.returncode != 0:
                print(f"  FAIL {sym} (exit={result.returncode})")
            else:
                print(f"  DONE {sym} (P&L: ${pnl:+,.0f})")

        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT {sym}")
            session.record_sim(sym, 0.0)
            stats['total_sims'] += 1
            stats['day_pnl'][date] = stats['day_pnl'].get(date, 0)
            stats['sim_details'].append((date, sym, profile, 0.0))

    print(f"  SESSION [{date}]: {session.summary()}")
    stats['session_summaries'][date] = session.summary()
    stats['session_details'][date] = {
        'stopped': session.stopped,
        'stop_reason': session.stop_reason,
        'session_pnl': session.session_pnl,
        'peak_pnl': session.peak_pnl,
        'sims': [(s, p) for s, p in session.sim_results],
    }


def main():
    print("=" * 60)
    print("  GIANT BACKTEST V2 — WITH PROTECTIVE FILTERS")
    print("=" * 60)

    stats = {
        'total_pnl': 0.0,
        'total_sims': 0,
        'winners': 0,
        'losers': 0,
        'cold_market_days': 0,
        'kill_switch_days': 0,
        'pm_vol_filtered': 0,
        'float_filtered': 0,
        'day_pnl': {},
        'sim_details': [],
        'session_summaries': {},
        'session_details': {},
    }

    for date in ALL_DATES:
        print(f"\n{'=' * 42}")
        print(f"Processing {date}")
        print(f"{'=' * 42}")
        process_date(date, stats)

    # ─── FINAL SUMMARY ───
    print("\n" + "=" * 60)
    print("  BACKTEST V2 SUMMARY")
    print("=" * 60)
    total = stats['total_sims']
    win_rate = (stats['winners'] / total * 100) if total > 0 else 0
    profitable_days = sum(1 for p in stats['day_pnl'].values() if p > 0)
    total_days_traded = len(stats['day_pnl'])
    print(f"  Total P&L:         ${stats['total_pnl']:+,.0f}")
    print(f"  Total Sims:        {total}")
    print(f"  Winners:           {stats['winners']}")
    print(f"  Losers:            {stats['losers']}")
    print(f"  Win Rate:          {win_rate:.1f}%")
    print(f"  Profitable Days:   {profitable_days}/{total_days_traded}")
    print(f"  Cold Market Skips: {stats['cold_market_days']}")
    print(f"  Kill Switch Fires: {stats['kill_switch_days']}")
    print(f"  PM Vol Filtered:   {stats['pm_vol_filtered']} stocks")
    print(f"  Float >10M Filter: {stats['float_filtered']} stocks")
    print()

    # Save stats for report generation
    report_data = {
        'total_pnl': stats['total_pnl'],
        'total_sims': stats['total_sims'],
        'winners': stats['winners'],
        'losers': stats['losers'],
        'win_rate': win_rate,
        'cold_market_days': stats['cold_market_days'],
        'kill_switch_days': stats['kill_switch_days'],
        'pm_vol_filtered': stats['pm_vol_filtered'],
        'float_filtered': stats['float_filtered'],
        'day_pnl': stats['day_pnl'],
        'sim_details': stats['sim_details'],
        'session_summaries': stats['session_summaries'],
        'session_details': {
            d: {
                'stopped': v['stopped'],
                'stop_reason': v['stop_reason'],
                'session_pnl': v['session_pnl'],
                'peak_pnl': v['peak_pnl'],
                'sims': v['sims'],
            }
            for d, v in stats['session_details'].items()
        },
        'profitable_days': profitable_days,
        'total_days_traded': total_days_traded,
    }
    with open('scanner_results/backtest_v2_stats.json', 'w') as f:
        json.dump(report_data, f, indent=2)
    print("Stats saved to scanner_results/backtest_v2_stats.json")


if __name__ == "__main__":
    main()
