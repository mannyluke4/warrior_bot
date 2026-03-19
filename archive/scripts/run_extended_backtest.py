#!/usr/bin/env python3
"""
Extended Backtest V4 — Oct 2025 → Feb 2026 (~105 trading days)

Extends the V4 backtest (Tier Restructure + B-Gate) from Jan-Feb 2026
to include Oct-Dec 2025. V4 rules are UNCHANGED:
  SQS 7-9 → Shelved → $250
  SQS 5-6 → A-tier  → $750
  SQS 4   → B-tier  → $250 (must pass quality gate: gap>=14% AND pm_vol>=10k)
  SQS 0-3 → Skip    → $0

Phase 1: Run scanner_sim.py for Oct-Dec 2025 dates (new)
Phase 2: Run V4 sims for Oct-Dec 2025 candidates
Phase 3: Load existing Jan-Feb V4 results from backtest_v4_stats.json
Phase 4: Combine into unified report + stats JSON with equity curve
"""

import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta

from session_manager import SessionManager

# ─── DATE GENERATION ───

# US market holidays where exchange is CLOSED (Oct 2025 - Dec 2025)
MARKET_HOLIDAYS_Q4_2025 = {
    date(2025, 11, 27),  # Thanksgiving
    date(2025, 12, 25),  # Christmas
}

# Half days (market open, early close at 1pm) — we still run these
HALF_DAYS_Q4_2025 = {
    date(2025, 11, 28),  # Black Friday
    date(2025, 12, 24),  # Christmas Eve
    date(2025, 12, 31),  # New Year's Eve
}


def generate_trading_days(start: date, end: date, holidays: set) -> list[str]:
    """Generate trading days (weekdays minus holidays) as YYYY-MM-DD strings."""
    days = []
    current = start
    while current <= end:
        # Skip weekends (5=Sat, 6=Sun) and holidays
        if current.weekday() < 5 and current not in holidays:
            days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return days


# Oct 1 - Dec 31, 2025
OCT_DEC_DATES = generate_trading_days(
    date(2025, 10, 1), date(2025, 12, 31), MARKET_HOLIDAYS_Q4_2025
)

# Jan-Feb 2026 dates (from existing V4 run — DO NOT re-run)
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

MIN_PM_VOLUME = 1000


def compute_sqs(candidate: dict) -> tuple[int, str, int]:
    """
    Compute Stock Quality Score and return (sqs, tier_label, risk_dollars).
    V4 tier mapping (unchanged from run_backtest_v4.py).
    """
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

        if pmv < MIN_PM_VOLUME:
            filtered_pm_vol.append(f"{c['symbol']} (pm_vol={pmv})")
            stats['pm_vol_filtered'] += 1
            continue

        if p == 'A' and 0.5 <= flt <= 5.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 40.0:
            profile_a.append(c)
        elif p == 'B' and 5.0 <= flt <= 10.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 25.0:
            profile_b.append(c)
        elif p == 'B' and flt > 10.0:
            filtered_float.append(f"{c['symbol']} (float={flt}M)")
            stats['float_filtered'] += 1

    profile_a.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
    profile_b.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
    profile_b = profile_b[:2]

    if filtered_pm_vol:
        print(f"  PM Volume filtered: {', '.join(filtered_pm_vol)}")
    if filtered_float:
        print(f"  Float >10M filtered: {', '.join(filtered_float)}")

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
                print(f"  B-GATE SKIP {sym} (SQS={sqs}, gap={gap:.1f}%, pm_vol={pm_vol:,.0f}) — needs gap>=14% AND pm_vol>=10k")
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

        outfile = f"scanner_results/{date_str}_{sym}.txt"

        # Resume-safe: skip if already exists with matching risk
        cached = False
        if os.path.exists(outfile) and os.path.getsize(outfile) > 0:
            with open(outfile) as f:
                existing = f.read()
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

            n_candidates = len(candidates)
            c_gap = c.get('gap_pct', 0) or 0
            c_pmvol = c.get('pm_volume', 0) or 0
            toxic_args = f"--candidates {n_candidates} --gap {c_gap} --pmvol {c_pmvol}"

            if profile == "B":
                cmd = f"timeout 180 python simulate.py {sym} {date_str} {sim_start} 12:00 --profile B --ticks --feed databento --l2 --no-fundamentals --risk {risk} {toxic_args}"
            else:
                cmd = f"timeout 120 python simulate.py {sym} {date_str} {sim_start} 12:00 --profile A --ticks --no-fundamentals --risk {risk} {toxic_args}"

            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=200)
                output = result.stdout + result.stderr

                if profile == "B" and (result.returncode != 0 or "license_not_found" in output or "403" in output or "Error" in output):
                    print(f"  WARN {sym} Databento failed, falling back to Alpaca")
                    cmd = f"timeout 120 python simulate.py {sym} {date_str} {sim_start} 12:00 --profile B --ticks --no-fundamentals --risk {risk} {toxic_args}"
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=140)
                    output = result.stdout + result.stderr

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


def load_jan_feb_results(stats: dict):
    """Load existing Jan-Feb V4 results from backtest_v4_stats.json."""
    v4_path = "scanner_results/backtest_v4_stats.json"
    if not os.path.exists(v4_path):
        print("ERROR: backtest_v4_stats.json not found — cannot load Jan-Feb results")
        sys.exit(1)

    with open(v4_path) as f:
        v4 = json.load(f)

    print(f"\n  Loaded Jan-Feb V4: {v4['total_sims']} sims, P&L=${v4['total_pnl']:+,.0f}")

    stats['total_pnl'] += v4['total_pnl']
    stats['total_sims'] += v4['total_sims']
    stats['winners'] += v4['winners']
    stats['losers'] += v4['losers']
    stats['cold_market_days'] += v4['cold_market_days']
    stats['kill_switch_days'] += v4['kill_switch_days']
    stats['pm_vol_filtered'] += v4.get('pm_vol_filtered', 0)
    stats['float_filtered'] += v4.get('float_filtered', 0)
    stats['sqs_skipped'] += v4.get('sqs_skipped', 0)
    stats['b_gate_skipped'] += v4.get('b_gate_skipped', 0)

    for d, p in v4['day_pnl'].items():
        stats['day_pnl'][d] = p

    for detail in v4['sim_details']:
        stats['sim_details'].append(tuple(detail))

    for d, summary in v4.get('session_summaries', {}).items():
        stats['session_summaries'][d] = summary

    for d, details in v4.get('session_details', {}).items():
        stats['session_details'][d] = details

    # SQS distribution
    v4_dist = v4.get('sqs_distribution', {})
    for key in ['shelved', 'a_tier', 'b_tier', 'b_gate_skip', 'skip']:
        stats['sqs_distribution'][key] += v4_dist.get(key, 0)

    # Tier P&L
    for tier, pnl in v4.get('tier_pnl', {}).items():
        stats['tier_pnl'][tier] = stats['tier_pnl'].get(tier, 0) + pnl


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
        if peak_balance > 0:
            dd_pct = drawdown / peak_balance * 100
        else:
            dd_pct = 0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_pct = dd_pct

        # Streaks
        if day_pnl > 0:
            win_streak += 1
            lose_streak = 0
        elif day_pnl < 0:
            lose_streak += 1
            win_streak = 0
        else:
            # Flat day ($0) — doesn't break either streak
            pass

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
        "buying_power_ratio": 4.0,
        "daily_balances": daily_balances,
    }


def compute_monthly_breakdown(stats: dict) -> dict:
    """Compute per-month stats."""
    months = {}
    for detail in stats['sim_details']:
        d, sym, prof, pnl, sqs, risk, tier = detail
        month_key = d[:7]  # "2025-10", "2026-01", etc.
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

    # Add cold market days that had no sims
    for d in ALL_DATES:
        month_key = d[:7]
        if month_key not in months:
            months[month_key] = {
                'pnl': 0.0, 'sims': 0, 'active': 0,
                'winners': 0, 'losers': 0, 'flat': 0,
                'days': set(),
            }
        months[month_key]['days'].add(d)

    # Compute best/worst day per month
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
        # Convert set to count for JSON serialization
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


def generate_report(stats: dict, equity: dict, monthly: dict, monsters: list):
    """Generate the unified Oct-Feb markdown report."""
    total = stats['total_sims']
    active = stats['winners'] + stats['losers']
    win_rate = (stats['winners'] / active * 100) if active > 0 else 0
    profitable_days = sum(1 for p in stats['day_pnl'].values() if p > 0)
    total_days_traded = len(stats['day_pnl'])
    total_days = len(ALL_DATES)

    lines = []
    lines.append("# Oct 2025 – Feb 2026 Backtest Report — V4 (Tier Restructure + B-Gate)")
    lines.append("")
    lines.append(f"**Generated:** 2026-03-09")
    lines.append(f"**Branch:** scanner-sim-backtest")
    lines.append(f"**Dates:** Oct 1, 2025 – Feb 27, 2026 ({total_days} trading days)")
    lines.append(f"**V4 Rules:** SQS tiers, B-gate, kill switch, cold market gate — ALL UNCHANGED")
    lines.append("")

    # ─── HEADLINE METRICS ───
    lines.append("## Headline Metrics")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| **Total P&L** | **${stats['total_pnl']:+,.0f}** |")
    lines.append(f"| Total Sims | {total} |")
    lines.append(f"| Active Trades (non-$0) | {active} |")
    lines.append(f"| Winners | {stats['winners']} |")
    lines.append(f"| Losers | {stats['losers']} |")
    lines.append(f"| Win Rate (active) | {win_rate:.1f}% |")
    lines.append(f"| Profitable Days | {profitable_days}/{total_days_traded} |")
    lines.append(f"| Trading Days (total) | {total_days} |")
    lines.append(f"| Cold Market Skips | {stats['cold_market_days']} |")
    lines.append(f"| Kill Switch Fires | {stats['kill_switch_days']} |")
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

    # ─── VERSION COMPARISON ───
    lines.append("## Version Comparison")
    lines.append("")
    lines.append("| Metric | V1 (No Filters) | V2 (Protective) | V3 (SQS+Sort) | V4 (Jan-Feb) | **V4 (Oct-Feb)** |")
    lines.append("|--------|-----------------|-----------------|---------------|--------------|-----------------|")
    lines.append(f"| **Total P&L** | -$17,885 | -$8,938 | +$566 | +$5,402 | **${stats['total_pnl']:+,.0f}** |")
    lines.append(f"| Total Sims | 51 | 161 | 26 | 63 | {total} |")
    lines.append(f"| Win Rate | 17.6% | 4.3% | 34.6% | 6.3% | {win_rate:.1f}% |")
    lines.append(f"| Cold Market Skips | 0 | 8 | 8 | 8 | {stats['cold_market_days']} |")
    lines.append(f"| Kill Switch Fires | 0 | 2 | 2 | 0 | {stats['kill_switch_days']} |")
    lines.append("")

    # ─── TIER PERFORMANCE ───
    lines.append("## Tier Performance")
    lines.append("")
    dist = stats['sqs_distribution']

    # Compute per-tier wins/losses
    tier_stats = {}
    for detail in stats['sim_details']:
        d, sym, prof, pnl, sqs, risk, tier = detail
        if tier not in tier_stats:
            tier_stats[tier] = {'sims': 0, 'active': 0, 'winners': 0, 'losers': 0, 'pnl': 0.0, 'wins_pnl': 0.0, 'losses_pnl': 0.0}
        ts = tier_stats[tier]
        ts['sims'] += 1
        ts['pnl'] += pnl
        if pnl > 0:
            ts['winners'] += 1
            ts['active'] += 1
            ts['wins_pnl'] += pnl
        elif pnl < 0:
            ts['losers'] += 1
            ts['active'] += 1
            ts['losses_pnl'] += pnl

    lines.append("| Tier | Sims | Active | W/L | P&L | Avg Win | Avg Loss |")
    lines.append("|------|------|--------|-----|-----|---------|----------|")
    for tier_name in ['Shelved', 'A', 'B']:
        ts = tier_stats.get(tier_name, {'sims': 0, 'active': 0, 'winners': 0, 'losers': 0, 'pnl': 0.0, 'wins_pnl': 0.0, 'losses_pnl': 0.0})
        avg_win = (ts['wins_pnl'] / ts['winners']) if ts['winners'] > 0 else 0
        avg_loss = (ts['losses_pnl'] / ts['losers']) if ts['losers'] > 0 else 0
        lines.append(f"| {tier_name} | {ts['sims']} | {ts['active']} | {ts['winners']}/{ts['losers']} | ${ts['pnl']:+,.0f} | ${avg_win:+,.0f} | ${avg_loss:+,.0f} |")
    lines.append("")

    # ─── SQS DISTRIBUTION ───
    lines.append("## SQS Distribution")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| Shelved (SQS 7-9, $250) | {dist['shelved']} |")
    lines.append(f"| A-tier (SQS 5-6, $750) | {dist['a_tier']} |")
    lines.append(f"| B-tier (SQS 4, $250, gate passed) | {dist['b_tier']} |")
    lines.append(f"| B-GATE SKIP (SQS 4, gate failed) | {dist['b_gate_skip']} |")
    lines.append(f"| SQS SKIP (0-3) | {dist['skip']} |")
    lines.append("")

    # ─── B-TIER GATE STATS ───
    b_total = dist['b_tier'] + dist['b_gate_skip']
    b_pnl = stats['tier_pnl'].get('B', 0)
    lines.append("## B-Tier Quality Gate Stats")
    lines.append("")
    lines.append(f"- SQS=4 candidates considered: **{b_total}**")
    lines.append(f"- Passed gate (gap>=14% AND pm_vol>=10k): **{dist['b_tier']}**")
    lines.append(f"- Blocked by gate: **{dist['b_gate_skip']}**")
    if dist['b_tier'] > 0:
        lines.append(f"- B-tier P&L (passed): **${b_pnl:+,.0f}**")
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
    lines.append(f"| Buying Power (4:1) | ${equity['ending_balance'] * 4:,.0f} |")
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

    # ─── KILL SWITCH ANALYSIS ───
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
    report_path = 'scanner_results/OCT_FEB_BACKTEST_REPORT_V4.md'
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\nReport saved to {report_path}")
    return report


def run_scanner_phase(dates: list[str]):
    """Phase 1: Run scanner_sim.py for dates that don't have JSONs yet."""
    print("\n" + "=" * 60)
    print("  PHASE 1: SCANNER (Oct-Dec 2025)")
    print("=" * 60)

    skipped = 0
    ran = 0
    for d in dates:
        json_path = f"scanner_results/{d}.json"
        if os.path.exists(json_path):
            skipped += 1
            continue

        print(f"\n  SCANNER {d}...")
        cmd = f"python scanner_sim.py --date {d}"
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                if os.path.exists(json_path):
                    print(f"  DONE {d}")
                    ran += 1
                else:
                    print(f"  WARN {d} — scanner finished but no JSON produced")
                    # Create empty JSON so we don't re-run
                    with open(json_path, 'w') as f:
                        json.dump([], f)
                    ran += 1
            else:
                print(f"  FAIL {d} (exit={result.returncode})")
                stderr_tail = result.stderr[-200:] if result.stderr else ""
                if stderr_tail:
                    print(f"    stderr: {stderr_tail}")
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT {d}")

    print(f"\n  Scanner phase complete: {ran} new, {skipped} cached")


def main():
    print("=" * 60)
    print("  EXTENDED BACKTEST V4 — OCT 2025 → FEB 2026")
    print(f"  Total trading days: {len(ALL_DATES)}")
    print(f"  Oct-Dec 2025 (new): {len(OCT_DEC_DATES)}")
    print(f"  Jan-Feb 2026 (existing): {len(JAN_FEB_DATES)}")
    print("=" * 60)

    # ─── PHASE 1: Scanner for Oct-Dec ───
    run_scanner_phase(OCT_DEC_DATES)

    # ─── PHASE 2: V4 sims for Oct-Dec ───
    print("\n" + "=" * 60)
    print("  PHASE 2: V4 SIMULATIONS (Oct-Dec 2025)")
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

    for d in OCT_DEC_DATES:
        print(f"\n{'=' * 42}")
        print(f"Processing {d}")
        print(f"{'=' * 42}")
        process_date(d, stats)

    oct_dec_pnl = stats['total_pnl']
    oct_dec_sims = stats['total_sims']
    print(f"\n  Oct-Dec phase complete: {oct_dec_sims} sims, P&L=${oct_dec_pnl:+,.0f}")

    # ─── PHASE 3: Load Jan-Feb results ───
    print("\n" + "=" * 60)
    print("  PHASE 3: LOADING JAN-FEB V4 RESULTS")
    print("=" * 60)

    load_jan_feb_results(stats)

    # ─── PHASE 4: Equity curve ───
    print("\n" + "=" * 60)
    print("  PHASE 4: EQUITY CURVE")
    print("=" * 60)

    equity = compute_equity_curve(stats)
    print(f"  $30,000 → ${equity['ending_balance']:,.0f} ({equity['total_return_pct']:+.1f}%)")
    print(f"  Peak: ${equity['peak_balance']:,.0f} ({equity['peak_date']})")
    print(f"  Max drawdown: ${equity['max_drawdown']:,.0f} ({equity['max_drawdown_pct']:.1f}%)")

    # ─── PHASE 5: Monthly breakdown + monsters ───
    monthly = compute_monthly_breakdown(stats)
    monsters = find_monster_trades(stats)

    # ─── PHASE 6: Report ───
    print("\n" + "=" * 60)
    print("  PHASE 5: GENERATING REPORT")
    print("=" * 60)

    generate_report(stats, equity, monthly, monsters)

    # ─── PHASE 7: Stats JSON ───
    total = stats['total_sims']
    active = stats['winners'] + stats['losers']
    win_rate = (stats['winners'] / active * 100) if active > 0 else 0
    profitable_days = sum(1 for p in stats['day_pnl'].values() if p > 0)
    total_days_traded = len(stats['day_pnl'])

    # Convert monthly sets for JSON
    monthly_json = {}
    for mk, m in monthly.items():
        monthly_json[mk] = {k: v for k, v in m.items()}

    report_data = {
        'total_pnl': stats['total_pnl'],
        'total_sims': stats['total_sims'],
        'winners': stats['winners'],
        'losers': stats['losers'],
        'win_rate': win_rate,
        'profitable_days': profitable_days,
        'total_days_traded': total_days_traded,
        'total_days': len(ALL_DATES),
        'cold_market_days': stats['cold_market_days'],
        'kill_switch_days': stats['kill_switch_days'],
        'pm_vol_filtered': stats['pm_vol_filtered'],
        'float_filtered': stats['float_filtered'],
        'sqs_skipped': stats['sqs_skipped'],
        'b_gate_skipped': stats['b_gate_skipped'],
        'sqs_distribution': stats['sqs_distribution'],
        'tier_pnl': stats['tier_pnl'],
        'day_pnl': stats['day_pnl'],
        'sim_details': [list(d) for d in stats['sim_details']],
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
        'monthly_breakdown': monthly_json,
        'equity_curve': equity,
        'monster_trades': monsters,
    }

    stats_path = 'scanner_results/oct_feb_v4_stats.json'
    with open(stats_path, 'w') as f:
        json.dump(report_data, f, indent=2)
    print(f"Stats saved to {stats_path}")

    # ─── FINAL SUMMARY ───
    print("\n" + "=" * 60)
    print("  EXTENDED BACKTEST V4 SUMMARY (Oct 2025 → Feb 2026)")
    print("=" * 60)
    print(f"  Total P&L:         ${stats['total_pnl']:+,.0f}")
    print(f"  Oct-Dec P&L:       ${oct_dec_pnl:+,.0f}")
    print(f"  Jan-Feb P&L:       +$5,402 (existing V4)")
    print(f"  Total Sims:        {total}")
    print(f"  Active Trades:     {active}")
    print(f"  Win Rate (active): {win_rate:.1f}%")
    print(f"  Profitable Days:   {profitable_days}/{total_days_traded}")
    print(f"  Cold Market Skips: {stats['cold_market_days']}")
    print(f"  Kill Switch Fires: {stats['kill_switch_days']}")
    print(f"")
    print(f"  Equity: $30,000 → ${equity['ending_balance']:,.0f} ({equity['total_return_pct']:+.1f}%)")
    print(f"  Peak: ${equity['peak_balance']:,.0f} | Max DD: ${equity['max_drawdown']:,.0f} ({equity['max_drawdown_pct']:.1f}%)")
    print(f"  Monster trades: {len(monsters)} (|P&L| > $1,000)")
    print()

    dist = stats['sqs_distribution']
    print(f"  SQS Distribution:  Shelved={dist['shelved']} A={dist['a_tier']} B={dist['b_tier']} B-Gate-Skip={dist['b_gate_skip']} Skip={dist['skip']}")
    for tier in ['Shelved', 'A', 'B']:
        pnl = stats['tier_pnl'].get(tier, 0)
        print(f"    {tier} tier P&L: ${pnl:+,.0f}")
    print()


if __name__ == "__main__":
    main()
