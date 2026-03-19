#!/usr/bin/env python3
"""
Giant Backtest V4 — Tier Restructure & C-Tier Tightening

Changes from V3:
- SQS 7-9 → Shelved ($250, was A+ $1000) — insufficient data at n=1
- SQS 5-6 → A-tier ($750, was B $500) — proven 42.9% WR, 4.8x R:R
- SQS 4   → B-tier ($250, was C $250) — must pass quality gate
- SQS 0-3 → Skip (was SQS 0-2) — SQS=3 demoted (-$998 across 35 sims)
- B-tier quality gate: gap >= 14% AND pm_vol >= 10,000

All other filters unchanged: cold market gate, kill switch, PM vol min, B ceiling 10M.
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


def compute_sqs(candidate: dict) -> tuple[int, str, int]:
    """
    Compute Stock Quality Score and return (sqs, tier_label, risk_dollars).

    V4 tier mapping:
      SQS 7-9 → "Shelved" → $250   (was $1000 — insufficient data at n=1)
      SQS 5-6 → "A"       → $750   (was $500  — proven 42.9% WR, 4.8x R:R)
      SQS 4   → "B"       → $250   (was $250  — must also pass quality gate)
      SQS 0-3 → "Skip"    → $0     (was SQS 0-2 — SQS=3 demoted)
    """
    pm_vol = candidate.get('pm_volume', 0) or 0
    gap = candidate.get('gap_pct', 0) or 0
    flt = candidate.get('float_millions')

    # PM Volume score (0-3) — unchanged
    if pm_vol >= 500_000:
        pm_score = 3
    elif pm_vol >= 50_000:
        pm_score = 2
    elif pm_vol >= 1_000:
        pm_score = 1
    else:
        pm_score = 0

    # Gap % score (0-3) — unchanged
    if gap >= 40:
        gap_score = 3
    elif gap >= 20:
        gap_score = 2
    elif gap >= 10:
        gap_score = 1
    else:
        gap_score = 0

    # Float score (0-3) — unchanged
    if flt is None or flt > 5.0:
        float_score = 0
    elif flt > 2.0:
        float_score = 1
    elif flt >= 0.5:
        float_score = 2
    else:
        float_score = 3

    sqs = pm_score + gap_score + float_score

    # V4 tier mapping
    if sqs >= 7:
        return sqs, "Shelved", 250    # was $1000
    elif sqs >= 5:
        return sqs, "A", 750          # was $500
    elif sqs >= 4:
        return sqs, "B", 250          # same $250, but requires quality gate
    else:
        return sqs, "Skip", 0         # was SQS 0-2, now SQS 0-3


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

    # V3: Sort by PM volume descending (unchanged)
    profile_a.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
    profile_b.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
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

        # V4: Compute Stock Quality Score (returns tier label)
        sqs, tier, risk = compute_sqs(c)

        # V6.2: Profile B risk cap — mid-float stocks capped at $250 regardless of SQS
        if profile == 'B' and risk > 250:
            risk = 250

        if risk == 0:
            pmv = c.get('pm_volume', 0)
            print(f"  SQS SKIP {sym} (SQS={sqs})")
            stats['sqs_skipped'] += 1
            stats['sqs_distribution']['skip'] += 1
            continue

        # V4: B-tier quality gate
        # SQS=4 stocks must have gap >= 14% AND PM volume >= 10,000
        if tier == "B":
            pm_vol = c.get('pm_volume', 0) or 0
            gap = c.get('gap_pct', 0) or 0
            if gap < 14.0 or pm_vol < 10_000:
                print(f"  B-GATE SKIP {sym} (SQS={sqs}, gap={gap:.1f}%, pm_vol={pm_vol:,.0f}) — needs gap>=14% AND pm_vol>=10k")
                stats['b_gate_skipped'] += 1
                stats['sqs_distribution']['b_gate_skip'] += 1
                continue

        # Check kill switch BEFORE running sim
        if session.should_stop():
            idx = all_candidates.index(c)
            remaining = [x['symbol'] for x in all_candidates[idx:]]
            print(f"  KILL SWITCH [{date}]: {session.stop_reason}")
            print(f"  Skipping: {', '.join(remaining)}")
            stats['kill_switch_days'] += 1
            break

        outfile = f"scanner_results/{date}_{sym}.txt"

        # Resume-safe: skip if already exists, has content, and was run with same risk
        cached = False
        if os.path.exists(outfile) and os.path.getsize(outfile) > 0:
            with open(outfile) as f:
                existing = f.read()
            # Check if risk matches (V4 embeds risk in output header)
            if f"--risk {risk}" in existing or f"risk={risk}" in existing:
                pnl = parse_pnl_from_output(existing)
                session.record_sim(sym, pnl)
                gate_str = " [B-GATE: PASS]" if tier == "B" else ""
                print(f"  CACHED {sym} SQS={sqs}({tier}) risk=${risk}{gate_str} (P&L: ${pnl:+,.0f})")
                cached = True

        if not cached:
            pmv = c.get('pm_volume', 0)
            gap = c.get('gap_pct', 0)
            flt = c.get('float_millions', 0)
            gate_str = " [B-GATE: PASS]" if tier == "B" else ""
            print(f"  RUN  {sym} profile={profile} start={sim_start} SQS={sqs}({tier}) risk=${risk} pm_vol={pmv:,.0f} gap={gap:.1f}% float={flt:.2f}M{gate_str}")

            # Build simulate.py command — with dynamic risk
            if profile == "B":
                cmd = f"timeout 180 python simulate.py {sym} {date} {sim_start} 12:00 --profile B --ticks --feed databento --l2 --no-fundamentals --risk {risk}"
            else:
                cmd = f"timeout 120 python simulate.py {sym} {date} {sim_start} 12:00 --profile A --ticks --no-fundamentals --risk {risk}"

            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=200)
                output = result.stdout + result.stderr

                # Profile B Databento fallback
                if profile == "B" and (result.returncode != 0 or "license_not_found" in output or "403" in output or "Error" in output):
                    print(f"  WARN {sym} Databento failed, falling back to Alpaca")
                    cmd = f"timeout 120 python simulate.py {sym} {date} {sim_start} 12:00 --profile B --ticks --no-fundamentals --risk {risk}"
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=140)
                    output = result.stdout + result.stderr

                # Write output with risk tag for resume-safe check
                with open(outfile, 'w') as f:
                    f.write(f"# V4 risk={risk} sqs={sqs} tier={tier}\n")
                    f.write(output)

                pnl = parse_pnl_from_output(output)
                session.record_sim(sym, pnl)

                if result.returncode != 0:
                    print(f"  FAIL {sym} (exit={result.returncode})")
                else:
                    print(f"  DONE {sym} (P&L: ${pnl:+,.0f})")

            except subprocess.TimeoutExpired:
                print(f"  TIMEOUT {sym}")
                session.record_sim(sym, 0.0)
                pnl = 0.0

        # Record stats
        stats['total_pnl'] += pnl
        stats['total_sims'] += 1
        if pnl > 0:
            stats['winners'] += 1
        elif pnl < 0:
            stats['losers'] += 1
        stats['day_pnl'][date] = stats['day_pnl'].get(date, 0) + pnl
        stats['sim_details'].append((date, sym, profile, pnl, sqs, risk, tier))

        # SQS distribution
        if tier == "Shelved":
            stats['sqs_distribution']['shelved'] += 1
        elif tier == "A":
            stats['sqs_distribution']['a_tier'] += 1
        elif tier == "B":
            stats['sqs_distribution']['b_tier'] += 1

        # Tier P&L
        stats['tier_pnl'][tier] = stats['tier_pnl'].get(tier, 0) + pnl

    print(f"  SESSION [{date}]: {session.summary()}")
    stats['session_summaries'][date] = session.summary()
    stats['session_details'][date] = {
        'stopped': session.stopped,
        'stop_reason': session.stop_reason,
        'session_pnl': session.session_pnl,
        'peak_pnl': session.peak_pnl,
        'sims': [(s, p) for s, p in session.sim_results],
    }


def generate_report(stats: dict):
    """Generate the V4 markdown report."""
    total = stats['total_sims']
    win_rate = (stats['winners'] / total * 100) if total > 0 else 0
    profitable_days = sum(1 for p in stats['day_pnl'].values() if p > 0)
    total_days_traded = len(stats['day_pnl'])

    lines = []
    lines.append("# Jan/Feb 2026 Backtest Report — V4 (Tier Restructure + B-Gate)")
    lines.append("")
    lines.append(f"**Generated:** 2026-03-09")
    lines.append(f"**Branch:** scanner-sim-backtest")
    lines.append(f"**Dates:** Jan 2 – Feb 27, 2026 (38 trading days)")
    lines.append("")

    # V1/V2/V3/V4 comparison
    lines.append("## Version Comparison")
    lines.append("")
    lines.append("| Metric | V1 (No Filters) | V2 (Protective) | V3 (SQS + PM Sort) | V4 (Tier Restructure) |")
    lines.append("|--------|-----------------|-----------------|---------------------|----------------------|")
    lines.append(f"| **Total P&L** | -$17,885 | -$8,938 | +$566 | **${stats['total_pnl']:+,.0f}** |")
    lines.append(f"| Total Sims | 51 | 161 | 26 | {total} |")
    lines.append(f"| Winners | 9 | 7 | 9 | {stats['winners']} |")
    lines.append(f"| Losers | — | 18 | 11 | {stats['losers']} |")
    lines.append(f"| Win Rate | 17.6% | 4.3% | 34.6% | {win_rate:.1f}% |")
    lines.append(f"| Profitable Days | 2/19 | 3/30 | 5/14 | {profitable_days}/{total_days_traded} |")
    lines.append(f"| Cold Market Skips | 0 | 8 | 8 | {stats['cold_market_days']} |")
    lines.append(f"| Kill Switch Fires | 0 | 2 | 2 | {stats['kill_switch_days']} |")
    lines.append("")

    # V4 Tier Mapping
    lines.append("## V4 Tier Mapping")
    lines.append("")
    lines.append("| Tier | SQS Range | Risk | Change from V3 |")
    lines.append("|------|-----------|------|---------------|")
    lines.append("| Shelved | 7-9 | $250 | Was A+ $1,000 — demoted (n=1 active trade) |")
    lines.append("| A-tier | 5-6 | $750 | Was B $500 — promoted (42.9% WR, 4.8x R:R) |")
    lines.append("| B-tier | 4 | $250 | Was C $250 — must pass quality gate |")
    lines.append("| Skip | 0-3 | $0 | Was 0-2 — SQS=3 demoted (-$998 in V3) |")
    lines.append("")

    # SQS Distribution
    dist = stats['sqs_distribution']
    total_considered = dist['shelved'] + dist['a_tier'] + dist['b_tier'] + dist['b_gate_skip'] + dist['skip']
    lines.append("## SQS Distribution")
    lines.append("")
    lines.append("| Tier | Count | P&L |")
    lines.append("|------|-------|-----|")
    shelved_pnl = stats['tier_pnl'].get('Shelved', 0)
    a_pnl = stats['tier_pnl'].get('A', 0)
    b_pnl = stats['tier_pnl'].get('B', 0)
    lines.append(f"| Shelved (SQS 7-9, $250) | {dist['shelved']} | ${shelved_pnl:+,.0f} |")
    lines.append(f"| A-tier (SQS 5-6, $750) | {dist['a_tier']} | ${a_pnl:+,.0f} |")
    lines.append(f"| B-tier (SQS 4, $250) — gate passed | {dist['b_tier']} | ${b_pnl:+,.0f} |")
    lines.append(f"| B-GATE SKIP (SQS 4, gate failed) | {dist['b_gate_skip']} | N/A |")
    lines.append(f"| SQS SKIP (0-3) | {dist['skip']} | N/A |")
    lines.append(f"| **Total** | **{total_considered}** | **${stats['total_pnl']:+,.0f}** |")
    lines.append("")

    # B-tier gate stats
    b_total = dist['b_tier'] + dist['b_gate_skip']
    lines.append("## B-Tier Quality Gate Stats")
    lines.append("")
    lines.append(f"- SQS=4 candidates considered: **{b_total}**")
    lines.append(f"- Passed gate (gap>=14% AND pm_vol>=10k): **{dist['b_tier']}**")
    lines.append(f"- Blocked by gate: **{dist['b_gate_skip']}**")
    if dist['b_tier'] > 0:
        lines.append(f"- B-tier P&L (passed): **${b_pnl:+,.0f}**")
    lines.append("")

    # Kill switch analysis
    lines.append("## Kill Switch Analysis")
    lines.append("")
    for date, details in stats['session_details'].items():
        if details['stopped']:
            lines.append(f"- **{date}**: {details['stop_reason']}")
            sims_str = ", ".join(f"{s} ${p:+,.0f}" for s, p in details['sims'])
            lines.append(f"  - Sims before stop: {sims_str}")
    if stats['kill_switch_days'] == 0:
        lines.append("No kill switch activations.")
    lines.append("")

    # Per-day breakdown
    lines.append("## Per-Day Breakdown")
    lines.append("")
    lines.append("| Date | Day P&L | Sims | Details |")
    lines.append("|------|---------|------|---------|")

    day_details = {}
    for date, sym, prof, pnl, sqs, risk, tier in stats['sim_details']:
        if date not in day_details:
            day_details[date] = []
        gate_str = " [B-GATE:PASS]" if tier == "B" else ""
        day_details[date].append(f"{sym}:{prof} SQS={sqs}({tier}) ${risk} P&L=${pnl:+,.0f}{gate_str}")

    for date in sorted(stats['day_pnl'].keys()):
        day_pnl = stats['day_pnl'][date]
        details = day_details.get(date, [])
        n_sims = len(details)
        detail_str = "; ".join(details)
        lines.append(f"| {date} | ${day_pnl:+,.0f} | {n_sims} | {detail_str} |")

    # Cold market days
    lines.append("")
    lines.append("## Cold Market Days Skipped")
    lines.append("")
    for date in ALL_DATES:
        if date not in stats['day_pnl'] and date not in [d for d in ALL_DATES if not os.path.exists(f"scanner_results/{date}.json")]:
            lines.append(f"- {date}")
    lines.append("")

    # Per-sim detail
    lines.append("## Per-Sim Detail")
    lines.append("")
    lines.append("```")
    for date, sym, prof, pnl, sqs, risk, tier in stats['sim_details']:
        gate_str = " [B-GATE:PASS]" if tier == "B" else ""
        lines.append(f"  {date} {sym:>6} :{prof} SQS={sqs}({tier}) risk=${risk} P&L=${pnl:+,.0f}{gate_str}")
    lines.append("```")
    lines.append("")

    report = "\n".join(lines)

    with open('scanner_results/JAN_FEB_BACKTEST_REPORT_V4.md', 'w') as f:
        f.write(report)
    print(f"\nReport saved to scanner_results/JAN_FEB_BACKTEST_REPORT_V4.md")

    return report


def main():
    print("=" * 60)
    print("  GIANT BACKTEST V4 — TIER RESTRUCTURE + B-GATE")
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
        'sqs_skipped': 0,
        'b_gate_skipped': 0,
        'day_pnl': {},
        'sim_details': [],
        'session_summaries': {},
        'session_details': {},
        'sqs_distribution': {'shelved': 0, 'a_tier': 0, 'b_tier': 0, 'b_gate_skip': 0, 'skip': 0},
        'tier_pnl': {},
    }

    for date in ALL_DATES:
        print(f"\n{'=' * 42}")
        print(f"Processing {date}")
        print(f"{'=' * 42}")
        process_date(date, stats)

    # ─── FINAL SUMMARY ───
    total = stats['total_sims']
    win_rate = (stats['winners'] / total * 100) if total > 0 else 0
    profitable_days = sum(1 for p in stats['day_pnl'].values() if p > 0)
    total_days_traded = len(stats['day_pnl'])

    print("\n" + "=" * 60)
    print("  BACKTEST V4 SUMMARY")
    print("=" * 60)
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
    print(f"  SQS Skipped:       {stats['sqs_skipped']} stocks")
    print(f"  B-Gate Skipped:    {stats['b_gate_skipped']} stocks")
    print()
    dist = stats['sqs_distribution']
    print(f"  SQS Distribution:  Shelved={dist['shelved']} A={dist['a_tier']} B={dist['b_tier']} B-Gate-Skip={dist['b_gate_skip']} Skip={dist['skip']}")
    for tier in ['Shelved', 'A', 'B']:
        pnl = stats['tier_pnl'].get(tier, 0)
        print(f"    {tier} tier P&L: ${pnl:+,.0f}")
    print()

    # Save stats
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
        'sqs_skipped': stats['sqs_skipped'],
        'b_gate_skipped': stats['b_gate_skipped'],
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
        'sqs_distribution': stats['sqs_distribution'],
        'tier_pnl': stats['tier_pnl'],
    }
    with open('scanner_results/backtest_v4_stats.json', 'w') as f:
        json.dump(report_data, f, indent=2)
    print("Stats saved to scanner_results/backtest_v4_stats.json")

    # Generate report
    generate_report(stats)


if __name__ == "__main__":
    main()
