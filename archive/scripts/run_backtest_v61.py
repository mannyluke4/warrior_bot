#!/usr/bin/env python3
"""
V6.1 Full Re-Run — Toxic Entry Filters Applied to ALL 102 Days (Oct 2025 – Feb 2026)

Previous run: Oct-Dec ran fresh with filters, Jan-Feb loaded from V4 cache (no filters).
This run: ALL dates re-run fresh with toxic filters active.

Output: scanner_results/v6_toxic_full/DATE_TICKER.txt
Report: scanner_results/V6_TOXIC_FULL_REPORT.md

V4 rules UNCHANGED: SQS tiers, B-gate, cold market gate, kill switch, PM vol sort.
Toxic filters layer on top via --candidates, --gap, --pmvol args to simulate.py.
"""

import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta

from session_manager import SessionManager

# ─── DATE GENERATION ───

MARKET_HOLIDAYS = {
    date(2025, 11, 27),  # Thanksgiving
    date(2025, 12, 25),  # Christmas
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # MLK Day
    date(2026, 2, 16),   # Presidents' Day
}


def generate_trading_days(start: date, end: date, holidays: set) -> list[str]:
    """Generate trading days (weekdays minus holidays) as YYYY-MM-DD strings."""
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return days


# Use the exact same date lists as the original extended backtest
OCT_DEC_DATES = generate_trading_days(
    date(2025, 10, 1), date(2025, 12, 31),
    {date(2025, 11, 27), date(2025, 12, 25)}
)

JAN_FEB_DATES = [
    "2026-01-02", "2026-01-03", "2026-01-05", "2026-01-06", "2026-01-07",
    "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14",
    "2026-01-15", "2026-01-16", "2026-01-21", "2026-01-22", "2026-01-23",
    "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29",
    "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
    "2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13",
    "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23",
    "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27",
]

ALL_DATES = OCT_DEC_DATES + JAN_FEB_DATES

OUTPUT_DIR = "scanner_results/v6_toxic_full"

MIN_PM_VOLUME = 1000


def compute_sqs(candidate: dict) -> tuple[int, str, int]:
    """Compute Stock Quality Score and return (sqs, tier_label, risk_dollars)."""
    pm_vol = candidate.get('pm_volume', 0) or 0
    gap = candidate.get('gap_pct', 0) or 0
    flt = candidate.get('float_millions')

    if pm_vol >= 500_000:
        pm_score = 3
    elif pm_vol >= 50_000:
        pm_score = 2
    elif pm_vol >= 1_000:
        pm_score = 1
    else:
        pm_score = 0

    if gap >= 40:
        gap_score = 3
    elif gap >= 20:
        gap_score = 2
    elif gap >= 10:
        gap_score = 1
    else:
        gap_score = 0

    if flt is None or flt > 5.0:
        float_score = 0
    elif flt > 2.0:
        float_score = 1
    elif flt >= 0.5:
        float_score = 2
    else:
        float_score = 3

    sqs = pm_score + gap_score + float_score

    if sqs >= 7:
        return sqs, "Shelved", 250
    elif sqs >= 5:
        return sqs, "A", 750
    elif sqs >= 4:
        return sqs, "B", 250
    else:
        return sqs, "Skip", 0


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


def process_date(date_str: str, stats: dict):
    """Process a single date: filter candidates and run simulations."""
    json_path = f"scanner_results/{date_str}.json"
    if not os.path.exists(json_path):
        print(f"  SKIP — no scanner results")
        return

    with open(json_path) as f:
        candidates = json.load(f)

    # ─── COLD MARKET GATE ───
    cold, cold_reason = is_cold_market(candidates)
    if cold:
        print(f"  COLD MARKET SKIP [{date_str}]: {cold_reason}")
        stats['cold_market_days'] += 1
        return

    # ─── FILTER CANDIDATES ───
    profile_a = []
    profile_b = []

    for c in candidates:
        p = c.get('profile', 'X')
        flt = c.get('float_millions')
        gap = c['gap_pct']
        price = c['pm_price']
        pmv = c.get('pm_volume', 0)

        if flt is None or p == 'X':
            continue

        if pmv < MIN_PM_VOLUME:
            stats['pm_vol_filtered'] += 1
            continue

        if p == 'A' and 0.5 <= flt <= 5.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 40.0:
            profile_a.append(c)
        elif p == 'B' and 5.0 <= flt <= 10.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 25.0:
            profile_b.append(c)
        elif p == 'B' and flt > 10.0:
            stats['float_filtered'] += 1

    profile_a.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
    profile_b.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
    profile_b = profile_b[:2]

    all_candidates = profile_a + profile_b

    if not all_candidates:
        print(f"  No candidates passed filters for {date_str}")
        return

    # ─── SESSION MANAGER (KILL SWITCH) ───
    session = SessionManager()

    for c in all_candidates:
        sym = c['symbol']
        profile = c['profile']
        sim_start = c.get('sim_start', '07:00')

        sqs, tier, risk = compute_sqs(c)

        if risk == 0:
            print(f"  SQS SKIP {sym} (SQS={sqs})")
            stats['sqs_skipped'] += 1
            stats['sqs_distribution']['skip'] += 1
            continue

        # V4: B-tier quality gate
        if tier == "B":
            pm_vol = c.get('pm_volume', 0) or 0
            gap = c.get('gap_pct', 0) or 0
            if gap < 14.0 or pm_vol < 10_000:
                print(f"  B-GATE SKIP {sym} (SQS={sqs}, gap={gap:.1f}%, pm_vol={pm_vol:,.0f})")
                stats['b_gate_skipped'] += 1
                stats['sqs_distribution']['b_gate_skip'] += 1
                continue

        if session.should_stop():
            idx = all_candidates.index(c)
            remaining = [x['symbol'] for x in all_candidates[idx:]]
            print(f"  KILL SWITCH [{date_str}]: {session.stop_reason}")
            print(f"  Skipping: {', '.join(remaining)}")
            stats['kill_switch_days'] += 1
            break

        outfile = f"{OUTPUT_DIR}/{date_str}_{sym}.txt"

        # Resume-safe: skip if already exists with content
        cached = False
        pnl = 0.0
        if os.path.exists(outfile) and os.path.getsize(outfile) > 0:
            with open(outfile) as f:
                existing = f.read()
            pnl = parse_pnl_from_output(existing)
            session.record_sim(sym, pnl)
            gate_str = " [B-GATE: PASS]" if tier == "B" else ""
            print(f"  CACHED {sym} SQS={sqs}({tier}) risk=${risk}{gate_str} (P&L: ${pnl:+,.0f})")
            cached = True

        if not cached:
            gate_str = " [B-GATE: PASS]" if tier == "B" else ""
            print(f"  RUN  {sym} profile={profile} start={sim_start} SQS={sqs}({tier}) risk=${risk}{gate_str}")

            n_candidates = len(candidates)
            c_gap = c.get('gap_pct', 0) or 0
            c_pmvol = c.get('pm_volume', 0) or 0
            toxic_args = f"--candidates {n_candidates} --gap {c_gap} --pmvol {c_pmvol}"

            # Profile A: Alpaca ticks only (no databento)
            cmd = f"timeout 120 python simulate.py {sym} {date_str} {sim_start} 12:00 --profile {profile} --ticks --no-fundamentals --risk {risk} {toxic_args}"

            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=140)
                output = result.stdout + result.stderr

                with open(outfile, 'w') as f:
                    f.write(f"# V6.1 risk={risk} sqs={sqs} tier={tier} toxic_args: candidates={n_candidates} gap={c_gap} pmvol={c_pmvol}\n")
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
        stats['day_pnl'][date_str] = stats['day_pnl'].get(date_str, 0) + pnl
        stats['sim_details'].append((date_str, sym, profile, pnl, sqs, risk, tier))

        if tier == "Shelved":
            stats['sqs_distribution']['shelved'] += 1
        elif tier == "A":
            stats['sqs_distribution']['a_tier'] += 1
        elif tier == "B":
            stats['sqs_distribution']['b_tier'] += 1

        stats['tier_pnl'][tier] = stats['tier_pnl'].get(tier, 0) + pnl

    print(f"  SESSION [{date_str}]: {session.summary()}")
    stats['session_summaries'][date_str] = session.summary()
    stats['session_details'][date_str] = {
        'stopped': session.stopped,
        'stop_reason': session.stop_reason,
        'session_pnl': session.session_pnl,
        'peak_pnl': session.peak_pnl,
        'sims': [(s, p) for s, p in session.sim_results],
    }


def detect_toxic_filter_catches(stats: dict) -> dict:
    """Scan sim output files for toxic filter blocks/half-risk entries."""
    filter1_catches = []
    filter2_catches = []

    for detail in stats['sim_details']:
        d, sym, prof, pnl, sqs, risk, tier = detail
        outfile = f"{OUTPUT_DIR}/{d}_{sym}.txt"
        if not os.path.exists(outfile):
            continue
        with open(outfile) as f:
            content = f.read()

        # Look for TOXIC BLOCK log lines
        if "TOXIC BLOCK" in content or "TOXIC_FILTER_1" in content or "wide_r_crowded_day" in content:
            filter1_catches.append({
                'date': d, 'symbol': sym, 'pnl': pnl,
                'profile': prof, 'tier': tier,
            })

        if "TOXIC HALF" in content or "TOXIC_FILTER_2" in content or "cold_low_vol_small_gap" in content or "HALF_RISK" in content:
            filter2_catches.append({
                'date': d, 'symbol': sym, 'pnl': pnl,
                'profile': prof, 'tier': tier,
            })

    return {
        'filter1': filter1_catches,
        'filter2': filter2_catches,
    }


def compute_equity_curve(stats: dict) -> dict:
    """Track $30K account equity across all trading days."""
    STARTING_BALANCE = 30000

    balance = STARTING_BALANCE
    peak_balance = STARTING_BALANCE
    peak_date = ALL_DATES[0] if ALL_DATES else ""
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    daily_balances = []
    win_streak = 0
    lose_streak = 0
    max_win_streak = 0
    max_lose_streak = 0

    for d in sorted(ALL_DATES):
        day_pnl = stats['day_pnl'].get(d, 0.0)
        balance += day_pnl
        daily_balances.append([d, round(day_pnl, 2), round(balance, 2)])

        if balance > peak_balance:
            peak_balance = balance
            peak_date = d

        drawdown = peak_balance - balance
        dd_pct = (drawdown / peak_balance * 100) if peak_balance > 0 else 0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_pct = dd_pct

        if day_pnl > 0:
            win_streak += 1
            lose_streak = 0
        elif day_pnl < 0:
            lose_streak += 1
            win_streak = 0

        max_win_streak = max(max_win_streak, win_streak)
        max_lose_streak = max(max_lose_streak, lose_streak)

    return {
        "starting_balance": STARTING_BALANCE,
        "ending_balance": round(balance, 2),
        "total_return_pct": round((balance - STARTING_BALANCE) / STARTING_BALANCE * 100, 2),
        "peak_balance": round(peak_balance, 2),
        "peak_date": peak_date,
        "max_drawdown": round(max_drawdown, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "max_win_streak": max_win_streak,
        "max_lose_streak": max_lose_streak,
        "daily_balances": daily_balances,
    }


def compute_monthly_breakdown(stats: dict) -> dict:
    """Compute per-month stats."""
    months = {}
    for detail in stats['sim_details']:
        d, sym, prof, pnl, sqs, risk, tier = detail
        month_key = d[:7]
        if month_key not in months:
            months[month_key] = {
                'pnl': 0.0, 'sims': 0, 'active': 0,
                'winners': 0, 'losers': 0, 'flat': 0,
                'days': set(),
            }
        m = months[month_key]
        m['sims'] += 1
        m['pnl'] += pnl
        m['days'].add(d)
        if pnl > 0:
            m['winners'] += 1
            m['active'] += 1
        elif pnl < 0:
            m['losers'] += 1
            m['active'] += 1
        else:
            m['flat'] += 1

    for d in ALL_DATES:
        month_key = d[:7]
        if month_key not in months:
            months[month_key] = {
                'pnl': 0.0, 'sims': 0, 'active': 0,
                'winners': 0, 'losers': 0, 'flat': 0,
                'days': set(),
            }
        months[month_key]['days'].add(d)

    for month_key, m in months.items():
        month_days = {d: stats['day_pnl'].get(d, 0.0) for d in m['days']}
        traded_days = {d: p for d, p in month_days.items() if d in stats['day_pnl']}
        if traded_days:
            best_day = max(traded_days, key=traded_days.get)
            worst_day = min(traded_days, key=traded_days.get)
            m['best_day'] = f"{best_day} (${traded_days[best_day]:+,.0f})"
            m['worst_day'] = f"{worst_day} (${traded_days[worst_day]:+,.0f})"
        else:
            m['best_day'] = "N/A"
            m['worst_day'] = "N/A"
        m['total_days'] = len(m['days'])
        m['days_traded'] = len(traded_days)
        m['days'] = len(m['days'])

    return months


def find_monster_trades(stats: dict) -> list:
    """Find all trades with |P&L| > $1,000."""
    monsters = []
    for detail in stats['sim_details']:
        d, sym, prof, pnl, sqs, risk, tier = detail
        if abs(pnl) > 1000:
            monsters.append({
                'date': d, 'symbol': sym, 'profile': prof,
                'pnl': pnl, 'sqs': sqs, 'risk': risk, 'tier': tier,
            })
    monsters.sort(key=lambda x: x['pnl'], reverse=True)
    return monsters


def generate_report(stats: dict, equity: dict, monthly: dict, monsters: list, toxic_catches: dict):
    """Generate the V6.1 full backtest report."""
    total = stats['total_sims']
    active = stats['winners'] + stats['losers']
    win_rate = (stats['winners'] / active * 100) if active > 0 else 0
    profitable_days = sum(1 for p in stats['day_pnl'].values() if p > 0)
    total_days_traded = len(stats['day_pnl'])
    total_days = len(ALL_DATES)

    # V4 baseline numbers (from original extended backtest without toxic filters)
    V4_PNL = 5798.0
    V4_SIMS = 166
    V4_ACTIVE = 31
    V4_WR = 41.9
    V4_DRAWDOWN = 2987.0
    V4_DRAWDOWN_PCT = 9.8

    f1 = toxic_catches['filter1']
    f2 = toxic_catches['filter2']
    f1_saved = sum(abs(c['pnl']) for c in f1 if c['pnl'] < 0)
    f2_saved = sum(abs(c['pnl']) for c in f2 if c['pnl'] < 0)

    # Check MLEC and FEED
    mlec_blocked = any(c['symbol'] == 'MLEC' for c in f1)
    feed_blocked = any(c['symbol'] == 'FEED' for c in f1)

    lines = []
    lines.append("# V6.1 Toxic Entry Filters — Full Re-Run Report")
    lines.append("")
    lines.append(f"**Date:** 2026-03-09")
    lines.append(f"**Branch:** v6-dynamic-sizing")
    lines.append(f"**Dataset:** Oct 2025 – Feb 2026 ({total_days} trading days)")
    lines.append(f"**Change:** ALL {total_days} dates re-run fresh with toxic filters active")
    lines.append(f"**Previous:** Jan-Feb was loaded from V4 cache (filters not applied)")
    lines.append("")

    # ─── V4 vs V6.1 COMPARISON ───
    lines.append("## V4 Baseline vs V6.1 Full Comparison")
    lines.append("")
    lines.append("| Metric | V4 Baseline | V6.1 Full | Change |")
    lines.append("|--------|------------|-----------|--------|")
    lines.append(f"| **Total P&L** | **${V4_PNL:+,.0f}** | **${stats['total_pnl']:+,.0f}** | ${stats['total_pnl'] - V4_PNL:+,.0f} |")
    lines.append(f"| Total Sims | {V4_SIMS} | {total} | {total - V4_SIMS:+d} |")
    lines.append(f"| Active Trades | {V4_ACTIVE} | {active} | {active - V4_ACTIVE:+d} |")
    lines.append(f"| Win Rate | {V4_WR}% | {win_rate:.1f}% | {win_rate - V4_WR:+.1f}pp |")
    lines.append(f"| Max Drawdown | ${V4_DRAWDOWN:,.0f} ({V4_DRAWDOWN_PCT}%) | ${equity['max_drawdown']:,.0f} ({equity['max_drawdown_pct']:.1f}%) | ${equity['max_drawdown'] - V4_DRAWDOWN:+,.0f} |")
    lines.append(f"| Ending Equity | ${30000 + V4_PNL:,.0f} | ${equity['ending_balance']:,.0f} | ${stats['total_pnl'] - V4_PNL:+,.0f} |")
    lines.append("")

    # ─── FILTER 1 CATCHES ───
    lines.append("## Filter 1 Catches: Wide R% + Crowded Day → HARD BLOCK")
    lines.append(f"**Condition:** R% >= 5.0% AND scanner candidates >= 20")
    lines.append("")
    if f1:
        lines.append("| Date | Symbol | Profile | Tier | P&L | Saved |")
        lines.append("|------|--------|---------|------|-----|-------|")
        for c in sorted(f1, key=lambda x: x['date']):
            saved = abs(c['pnl']) if c['pnl'] < 0 else 0
            lines.append(f"| {c['date']} | {c['symbol']} | {c['profile']} | {c['tier']} | ${c['pnl']:+,.0f} | ${saved:,.0f} |")
        lines.append(f"| **Total** | | | | | **${f1_saved:,.0f}** |")
    else:
        lines.append("No Filter 1 catches detected in output files.")
        lines.append("(Note: blocked trades may show $0 P&L — check sim output for TOXIC BLOCK lines)")
    lines.append("")

    # ─── FILTER 2 CATCHES ───
    lines.append("## Filter 2 Catches: Cold + Low Vol + Small Gap → HALF RISK")
    lines.append(f"**Condition:** gap < 30% AND pm_volume < 100K AND month in {{Feb, Oct, Nov}}")
    lines.append("")
    if f2:
        lines.append("| Date | Symbol | Profile | Tier | P&L (half risk) | Estimated Full-Risk P&L | Saved |")
        lines.append("|------|--------|---------|------|-----------------|------------------------|-------|")
        for c in sorted(f2, key=lambda x: x['date']):
            est_full = c['pnl'] * 2  # rough estimate
            saved = abs(est_full - c['pnl']) if c['pnl'] < 0 else 0
            lines.append(f"| {c['date']} | {c['symbol']} | {c['profile']} | {c['tier']} | ${c['pnl']:+,.0f} | ~${est_full:+,.0f} | ~${saved:,.0f} |")
        f2_est_saved = sum(abs(c['pnl']) for c in f2 if c['pnl'] < 0)  # savings = half of loss avoided
        lines.append(f"| **Total** | | | | | | **~${f2_est_saved:,.0f}** |")
    else:
        lines.append("No Filter 2 catches detected in output files.")
    lines.append("")

    # ─── KEY TARGETS ───
    lines.append("## Key Jan-Feb Targets")
    lines.append("")
    lines.append(f"- MLEC 2026-01-16 (R%=7.1%, 25 candidates): **{'BLOCKED' if mlec_blocked else 'NOT BLOCKED'}**")
    lines.append(f"- FEED 2026-01-09 (R%=6.4%, 21 candidates): **{'BLOCKED' if feed_blocked else 'NOT BLOCKED'}**")
    lines.append("")

    # ─── MONTHLY BREAKDOWN ───
    lines.append("## Monthly Breakdown")
    lines.append("")
    lines.append("| Month | Days | Sims | Active | W/L | P&L | Best Day | Worst Day |")
    lines.append("|-------|------|------|--------|-----|-----|----------|-----------|")
    for mk in sorted(monthly.keys()):
        m = monthly[mk]
        lines.append(f"| {mk} | {m['total_days']} | {m['sims']} | {m['active']} | {m['winners']}/{m['losers']} | ${m['pnl']:+,.0f} | {m['best_day']} | {m['worst_day']} |")
    lines.append("")

    # ─── EQUITY CURVE ───
    lines.append("## Equity Curve Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Starting Balance | ${equity['starting_balance']:,.0f} |")
    lines.append(f"| Ending Balance | ${equity['ending_balance']:,.0f} |")
    lines.append(f"| Total Return | {equity['total_return_pct']:+.1f}% |")
    lines.append(f"| Peak Balance | ${equity['peak_balance']:,.0f} ({equity['peak_date']}) |")
    lines.append(f"| Max Drawdown | ${equity['max_drawdown']:,.0f} ({equity['max_drawdown_pct']:.1f}%) |")
    lines.append(f"| Max Win Streak | {equity['max_win_streak']} days |")
    lines.append(f"| Max Lose Streak | {equity['max_lose_streak']} days |")
    lines.append("")

    # ─── TIER PERFORMANCE ───
    lines.append("## Tier Performance")
    lines.append("")
    tier_stats = {}
    for detail in stats['sim_details']:
        d, sym, prof, pnl, sqs, risk, tier = detail
        if tier not in tier_stats:
            tier_stats[tier] = {'sims': 0, 'winners': 0, 'losers': 0, 'pnl': 0.0, 'wins_pnl': 0.0, 'losses_pnl': 0.0}
        ts = tier_stats[tier]
        ts['sims'] += 1
        ts['pnl'] += pnl
        if pnl > 0:
            ts['winners'] += 1
            ts['wins_pnl'] += pnl
        elif pnl < 0:
            ts['losers'] += 1
            ts['losses_pnl'] += pnl

    lines.append("| Tier | Sims | W/L | P&L | Avg Win | Avg Loss |")
    lines.append("|------|------|-----|-----|---------|----------|")
    for tier_name in ['Shelved', 'A', 'B']:
        ts = tier_stats.get(tier_name, {'sims': 0, 'winners': 0, 'losers': 0, 'pnl': 0.0, 'wins_pnl': 0.0, 'losses_pnl': 0.0})
        avg_win = (ts['wins_pnl'] / ts['winners']) if ts['winners'] > 0 else 0
        avg_loss = (ts['losses_pnl'] / ts['losers']) if ts['losers'] > 0 else 0
        lines.append(f"| {tier_name} | {ts['sims']} | {ts['winners']}/{ts['losers']} | ${ts['pnl']:+,.0f} | ${avg_win:+,.0f} | ${avg_loss:+,.0f} |")
    lines.append("")

    # ─── MONSTER TRADES ───
    lines.append("## Monster Trades (|P&L| > $1,000)")
    lines.append("")
    if monsters:
        winners = [m for m in monsters if m['pnl'] > 0]
        losers = [m for m in monsters if m['pnl'] < 0]
        lines.append(f"**{len(winners)} monster winners, {len(losers)} monster losers**")
        lines.append("")
        lines.append("| Date | Symbol | Profile | Tier | Risk | P&L |")
        lines.append("|------|--------|---------|------|------|-----|")
        for m in monsters:
            lines.append(f"| {m['date']} | {m['symbol']} | {m['profile']} | {m['tier']} (SQS={m['sqs']}) | ${m['risk']} | ${m['pnl']:+,.0f} |")
    else:
        lines.append("No monster trades found.")
    lines.append("")

    # ─── KILL SWITCH ───
    lines.append("## Kill Switch Analysis")
    lines.append("")
    found_kill = False
    for d in sorted(stats['session_details'].keys()):
        details = stats['session_details'][d]
        if details['stopped']:
            found_kill = True
            lines.append(f"- **{d}**: {details['stop_reason']}")
            sims_str = ", ".join(f"{s} ${p:+,.0f}" for s, p in details['sims'])
            lines.append(f"  - Sims before stop: {sims_str}")
    if not found_kill:
        lines.append("No kill switch activations.")
    lines.append("")

    # ─── PER-DAY BREAKDOWN ───
    lines.append("## Per-Day Breakdown")
    lines.append("")
    lines.append("| Date | Day P&L | Sims | Details |")
    lines.append("|------|---------|------|---------|")

    day_details = {}
    for detail in stats['sim_details']:
        d, sym, prof, pnl, sqs, risk, tier = detail
        if d not in day_details:
            day_details[d] = []
        gate_str = " [B-GATE:PASS]" if tier == "B" else ""
        day_details[d].append(f"{sym}:{prof} SQS={sqs}({tier}) ${risk} P&L=${pnl:+,.0f}{gate_str}")

    for d in sorted(stats['day_pnl'].keys()):
        day_pnl = stats['day_pnl'][d]
        details = day_details.get(d, [])
        n_sims = len(details)
        detail_str = "; ".join(details)
        lines.append(f"| {d} | ${day_pnl:+,.0f} | {n_sims} | {detail_str} |")

    lines.append("")

    # ─── PER-SIM DETAIL ───
    lines.append("## Per-Sim Detail")
    lines.append("")
    lines.append("```")
    for detail in sorted(stats['sim_details'], key=lambda x: x[0]):
        d, sym, prof, pnl, sqs, risk, tier = detail
        gate_str = " [B-GATE:PASS]" if tier == "B" else ""
        lines.append(f"  {d} {sym:>6} :{prof} SQS={sqs}({tier}) risk=${risk} P&L=${pnl:+,.0f}{gate_str}")
    lines.append("```")
    lines.append("")

    report = "\n".join(lines)
    report_path = 'scanner_results/V6_TOXIC_FULL_REPORT.md'
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\nReport saved to {report_path}")
    return report


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("  V6.1 FULL RE-RUN — TOXIC FILTERS ON ALL 102 DAYS")
    print(f"  Total trading days: {len(ALL_DATES)}")
    print(f"  Oct-Dec 2025: {len(OCT_DEC_DATES)}")
    print(f"  Jan-Feb 2026: {len(JAN_FEB_DATES)}")
    print(f"  Output: {OUTPUT_DIR}/")
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

    # ─── RUN ALL DATES FRESH ───
    for d in ALL_DATES:
        print(f"\n{'=' * 42}")
        print(f"Processing {d}")
        print(f"{'=' * 42}")
        process_date(d, stats)

    # ─── DETECT TOXIC FILTER CATCHES ───
    print("\n" + "=" * 60)
    print("  SCANNING FOR TOXIC FILTER CATCHES")
    print("=" * 60)
    toxic_catches = detect_toxic_filter_catches(stats)
    print(f"  Filter 1 (BLOCK): {len(toxic_catches['filter1'])} catches")
    print(f"  Filter 2 (HALF):  {len(toxic_catches['filter2'])} catches")

    # ─── EQUITY CURVE ───
    equity = compute_equity_curve(stats)
    monthly = compute_monthly_breakdown(stats)
    monsters = find_monster_trades(stats)

    # ─── REPORT ───
    print("\n" + "=" * 60)
    print("  GENERATING V6.1 FULL REPORT")
    print("=" * 60)
    generate_report(stats, equity, monthly, monsters, toxic_catches)

    # ─── STATS JSON ───
    total = stats['total_sims']
    active = stats['winners'] + stats['losers']
    win_rate = (stats['winners'] / active * 100) if active > 0 else 0

    report_data = {
        'total_pnl': stats['total_pnl'],
        'total_sims': stats['total_sims'],
        'winners': stats['winners'],
        'losers': stats['losers'],
        'win_rate': win_rate,
        'cold_market_days': stats['cold_market_days'],
        'kill_switch_days': stats['kill_switch_days'],
        'day_pnl': stats['day_pnl'],
        'sim_details': [list(d) for d in stats['sim_details']],
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
        'monthly_breakdown': {mk: {k: v for k, v in m.items()} for mk, m in monthly.items()},
        'equity_curve': equity,
        'monster_trades': monsters,
        'toxic_catches': {
            'filter1': toxic_catches['filter1'],
            'filter2': toxic_catches['filter2'],
        },
    }

    stats_path = f'{OUTPUT_DIR}/v61_full_stats.json'
    with open(stats_path, 'w') as f:
        json.dump(report_data, f, indent=2)
    print(f"Stats saved to {stats_path}")

    # ─── FINAL SUMMARY ───
    print("\n" + "=" * 60)
    print("  V6.1 FULL RE-RUN SUMMARY (Oct 2025 → Feb 2026)")
    print("=" * 60)
    print(f"  Total P&L:         ${stats['total_pnl']:+,.0f}")
    print(f"  Total Sims:        {total}")
    print(f"  Active Trades:     {active}")
    print(f"  Win Rate (active): {win_rate:.1f}%")
    print(f"  Cold Market Skips: {stats['cold_market_days']}")
    print(f"  Kill Switch Fires: {stats['kill_switch_days']}")
    print(f"")
    print(f"  Equity: $30,000 → ${equity['ending_balance']:,.0f} ({equity['total_return_pct']:+.1f}%)")
    print(f"  Peak: ${equity['peak_balance']:,.0f} | Max DD: ${equity['max_drawdown']:,.0f} ({equity['max_drawdown_pct']:.1f}%)")
    print(f"")
    print(f"  Filter 1 blocks: {len(toxic_catches['filter1'])}")
    print(f"  Filter 2 half-risk: {len(toxic_catches['filter2'])}")
    print(f"  Monster trades: {len(monsters)} (|P&L| > $1,000)")
    print()


if __name__ == "__main__":
    main()
