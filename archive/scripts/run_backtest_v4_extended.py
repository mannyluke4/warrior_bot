#!/usr/bin/env python3
"""
Extended Backtest V4 — Oct 2025 through Feb 2026 (~105 trading days)

Runs V4 (Tier Restructure + B-Gate) on Oct-Dec 2025 dates, then combines
with existing Jan-Feb 2026 results from backtest_v4_stats.json.

Adds equity curve tracking ($30K starting balance, 4:1 margin).
"""

import json
import os
import re
import subprocess
import sys

from session_manager import SessionManager

# Oct-Dec 2025 trading days (weekends removed, holidays noted)
OCT_DEC_DATES = [
    # October 2025
    "2025-10-01", "2025-10-02", "2025-10-03",
    "2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09", "2025-10-10",
    "2025-10-13", "2025-10-14", "2025-10-15", "2025-10-16", "2025-10-17",
    "2025-10-20", "2025-10-21", "2025-10-22", "2025-10-23", "2025-10-24",
    "2025-10-27", "2025-10-28", "2025-10-29", "2025-10-30", "2025-10-31",
    # November 2025
    "2025-11-03", "2025-11-04", "2025-11-05", "2025-11-06", "2025-11-07",
    "2025-11-10", "2025-11-11", "2025-11-12", "2025-11-13", "2025-11-14",
    "2025-11-17", "2025-11-18", "2025-11-19", "2025-11-20", "2025-11-21",
    "2025-11-24", "2025-11-25", "2025-11-26",
    # Nov 27 = Thanksgiving CLOSED
    "2025-11-28",  # half day
    # December 2025
    "2025-12-01", "2025-12-02", "2025-12-03", "2025-12-04", "2025-12-05",
    "2025-12-08", "2025-12-09", "2025-12-10", "2025-12-11", "2025-12-12",
    "2025-12-15", "2025-12-16", "2025-12-17", "2025-12-18", "2025-12-19",
    "2025-12-22", "2025-12-23", "2025-12-24",  # Christmas Eve half day
    # Dec 25 = Christmas CLOSED
    "2025-12-26",
    "2025-12-29", "2025-12-30", "2025-12-31",  # NYE half day
]

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

MIN_PM_VOLUME = 1000


def compute_sqs(candidate: dict) -> tuple[int, str, int]:
    """V4 tier mapping (same as run_backtest_v4.py)."""
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
    match = re.search(r'Gross P&L:\s*\$([+-]?[\d,]+)', output)
    if match:
        return float(match.group(1).replace(',', ''))
    return 0.0


def is_cold_market(candidates: list[dict]) -> tuple[bool, str]:
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
    json_path = f"scanner_results/{date}.json"
    if not os.path.exists(json_path):
        print(f"  SKIP — no scanner results")
        return

    with open(json_path) as f:
        candidates = json.load(f)

    # Cold market gate
    cold, cold_reason = is_cold_market(candidates)
    if cold:
        print(f"  COLD MARKET SKIP [{date}]: {cold_reason}")
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

    # Filter candidates
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
        print(f"  No candidates passed filters for {date}")
        return

    session = SessionManager()

    for c in all_candidates:
        sym = c['symbol']
        profile = c['profile']
        sim_start = c.get('sim_start', '07:00')

        sqs, tier, risk = compute_sqs(c)

        if risk == 0:
            stats['sqs_skipped'] += 1
            stats['sqs_distribution']['skip'] += 1
            print(f"  SQS SKIP {sym} (SQS={sqs})")
            continue

        # B-tier quality gate
        if tier == "B":
            pm_vol = c.get('pm_volume', 0) or 0
            gap = c.get('gap_pct', 0) or 0
            if gap < 14.0 or pm_vol < 10_000:
                print(f"  B-GATE SKIP {sym} (SQS={sqs}, gap={gap:.1f}%, pm_vol={pm_vol:,.0f})")
                stats['b_gate_skipped'] += 1
                stats['sqs_distribution']['b_gate_skip'] += 1
                continue

        # Kill switch
        if session.should_stop():
            idx = all_candidates.index(c)
            remaining = [x['symbol'] for x in all_candidates[idx:]]
            print(f"  KILL SWITCH [{date}]: {session.stop_reason}")
            print(f"  Skipping: {', '.join(remaining)}")
            stats['kill_switch_days'] += 1
            break

        outfile = f"scanner_results/{date}_{sym}.txt"

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

        if tier == "Shelved":
            stats['sqs_distribution']['shelved'] += 1
        elif tier == "A":
            stats['sqs_distribution']['a_tier'] += 1
        elif tier == "B":
            stats['sqs_distribution']['b_tier'] += 1

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


def merge_jan_feb(stats: dict):
    """Merge existing Jan-Feb V4 results into stats."""
    jf_path = "scanner_results/backtest_v4_stats.json"
    if not os.path.exists(jf_path):
        print("WARNING: No Jan-Feb V4 stats found!")
        return

    with open(jf_path) as f:
        jf = json.load(f)

    stats['total_pnl'] += jf['total_pnl']
    stats['total_sims'] += jf['total_sims']
    stats['winners'] += jf['winners']
    stats['losers'] += jf['losers']
    stats['cold_market_days'] += jf['cold_market_days']
    stats['kill_switch_days'] += jf['kill_switch_days']
    stats['pm_vol_filtered'] += jf.get('pm_vol_filtered', 0)
    stats['float_filtered'] += jf.get('float_filtered', 0)
    stats['sqs_skipped'] += jf.get('sqs_skipped', 0)
    stats['b_gate_skipped'] += jf.get('b_gate_skipped', 0)

    # Day P&L
    for d, p in jf['day_pnl'].items():
        stats['day_pnl'][d] = p

    # Sim details
    for detail in jf['sim_details']:
        stats['sim_details'].append(tuple(detail))

    # Session details
    for d, v in jf.get('session_details', {}).items():
        stats['session_details'][d] = v

    # Session summaries
    for d, v in jf.get('session_summaries', {}).items():
        stats['session_summaries'][d] = v

    # SQS distribution
    jf_dist = jf.get('sqs_distribution', {})
    for k in ['shelved', 'a_tier', 'b_tier', 'b_gate_skip', 'skip']:
        stats['sqs_distribution'][k] += jf_dist.get(k, 0)

    # Tier P&L
    for tier, pnl in jf.get('tier_pnl', {}).items():
        stats['tier_pnl'][tier] = stats['tier_pnl'].get(tier, 0) + pnl


def compute_equity_curve(stats: dict) -> dict:
    """Compute equity curve from daily P&L."""
    STARTING_BALANCE = 30000
    balance = STARTING_BALANCE
    peak_balance = STARTING_BALANCE
    max_drawdown = 0
    max_drawdown_pct = 0
    peak_date = None
    trough_date = None

    daily_balances = []
    winning_streak = 0
    losing_streak = 0
    max_winning_streak = 0
    max_losing_streak = 0
    current_streak_type = None  # 'win' or 'lose'
    current_streak = 0

    all_dates = sorted(stats['day_pnl'].keys())

    # Also include cold market days as $0 days for streak tracking
    all_trading_dates = sorted(set(all_dates) | set(OCT_DEC_DATES) | set(JAN_FEB_DATES))

    for date in all_trading_dates:
        day_pnl = stats['day_pnl'].get(date, 0)
        balance += day_pnl
        daily_balances.append([date, day_pnl, round(balance, 2)])

        if balance > peak_balance:
            peak_balance = balance
            peak_date = date

        drawdown = peak_balance - balance
        drawdown_pct = (drawdown / peak_balance * 100) if peak_balance > 0 else 0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_pct = drawdown_pct
            trough_date = date

        # Streak tracking (only on days with actual activity)
        if date in all_dates:
            if day_pnl > 0:
                if current_streak_type == 'win':
                    current_streak += 1
                else:
                    current_streak_type = 'win'
                    current_streak = 1
                max_winning_streak = max(max_winning_streak, current_streak)
            elif day_pnl < 0:
                if current_streak_type == 'lose':
                    current_streak += 1
                else:
                    current_streak_type = 'lose'
                    current_streak = 1
                max_losing_streak = max(max_losing_streak, current_streak)
            # $0 days don't break streaks

    return {
        "starting_balance": STARTING_BALANCE,
        "ending_balance": round(balance, 2),
        "total_return_pct": round(((balance - STARTING_BALANCE) / STARTING_BALANCE) * 100, 2),
        "peak_balance": round(peak_balance, 2),
        "peak_date": peak_date,
        "max_drawdown": round(max_drawdown, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "trough_date": trough_date,
        "max_winning_streak": max_winning_streak,
        "max_losing_streak": max_losing_streak,
        "daily_balances": daily_balances,
        "buying_power_ratio": 4.0,
    }


def compute_monthly_breakdown(stats: dict) -> dict:
    """Break down stats by month."""
    months = {}
    for date, sym, prof, pnl, sqs, risk, tier in stats['sim_details']:
        month_key = date[:7]  # "2025-10", etc.
        if month_key not in months:
            months[month_key] = {
                'pnl': 0, 'sims': 0, 'active': 0,
                'winners': 0, 'losers': 0, 'flat': 0,
                'day_pnls': {},
            }
        m = months[month_key]
        m['sims'] += 1
        m['pnl'] += pnl
        if pnl > 0:
            m['winners'] += 1
            m['active'] += 1
        elif pnl < 0:
            m['losers'] += 1
            m['active'] += 1
        else:
            m['flat'] += 1

        m['day_pnls'][date] = m['day_pnls'].get(date, 0) + pnl

    # Compute best/worst day per month
    for mk, m in months.items():
        if m['day_pnls']:
            best_day = max(m['day_pnls'].items(), key=lambda x: x[1])
            worst_day = min(m['day_pnls'].items(), key=lambda x: x[1])
            m['best_day'] = best_day
            m['worst_day'] = worst_day
            m['days_traded'] = len(m['day_pnls'])
            m['profitable_days'] = sum(1 for p in m['day_pnls'].values() if p > 0)
        else:
            m['best_day'] = ("N/A", 0)
            m['worst_day'] = ("N/A", 0)
            m['days_traded'] = 0
            m['profitable_days'] = 0

    return months


def find_monster_trades(stats: dict) -> list:
    """Find all trades with |P&L| > $1000."""
    monsters = []
    for date, sym, prof, pnl, sqs, risk, tier in stats['sim_details']:
        if abs(pnl) >= 1000:
            monsters.append({
                'date': date, 'symbol': sym, 'profile': prof,
                'pnl': pnl, 'sqs': sqs, 'risk': risk, 'tier': tier,
            })
    return sorted(monsters, key=lambda x: x['pnl'], reverse=True)


def generate_unified_report(stats: dict, equity: dict, monthly: dict, monsters: list):
    """Generate the unified Oct-Feb V4 report."""
    total = stats['total_sims']
    active = stats['winners'] + stats['losers']
    win_rate = (stats['winners'] / active * 100) if active > 0 else 0
    profitable_days = sum(1 for p in stats['day_pnl'].values() if p > 0)
    total_days_traded = len(stats['day_pnl'])
    # Count total calendar days processed (including cold market skips)
    all_dates_count = len(OCT_DEC_DATES) + len(JAN_FEB_DATES)

    lines = []
    lines.append("# Oct 2025 – Feb 2026 Backtest Report — V4 (Tier Restructure + B-Gate)")
    lines.append("")
    lines.append(f"**Generated:** 2026-03-09")
    lines.append(f"**Branch:** scanner-sim-backtest")
    lines.append(f"**Dates:** Oct 1, 2025 – Feb 27, 2026 ({all_dates_count} trading days)")
    lines.append(f"**Engine:** simulate.py --ticks (tick-by-tick replay)")
    lines.append("")

    # Headline metrics
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
    lines.append(f"| Cold Market Skips | {stats['cold_market_days']} |")
    lines.append(f"| Kill Switch Fires | {stats['kill_switch_days']} |")
    lines.append("")

    # Monthly breakdown
    lines.append("## Monthly Breakdown")
    lines.append("")
    lines.append("| Month | Days | Sims | Active | W/L | P&L | Best Day | Worst Day |")
    lines.append("|-------|------|------|--------|-----|-----|----------|-----------|")
    month_order = ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]
    month_labels = {"2025-10": "Oct 2025", "2025-11": "Nov 2025", "2025-12": "Dec 2025",
                    "2026-01": "Jan 2026", "2026-02": "Feb 2026"}
    for mk in month_order:
        m = monthly.get(mk, {'pnl': 0, 'sims': 0, 'active': 0, 'winners': 0, 'losers': 0,
                             'days_traded': 0, 'best_day': ('N/A', 0), 'worst_day': ('N/A', 0)})
        label = month_labels.get(mk, mk)
        bd = m['best_day']
        wd = m['worst_day']
        best_str = f"{bd[0]} ${bd[1]:+,.0f}" if bd[0] != "N/A" else "—"
        worst_str = f"{wd[0]} ${wd[1]:+,.0f}" if wd[0] != "N/A" else "—"
        lines.append(f"| {label} | {m.get('days_traded', 0)} | {m['sims']} | {m.get('active', 0)} | {m['winners']}/{m['losers']} | ${m['pnl']:+,.0f} | {best_str} | {worst_str} |")
    lines.append("")

    # Version comparison
    lines.append("## Version Comparison")
    lines.append("")
    lines.append("| Metric | V1 (No Filters) | V2 (Protective) | V3 (SQS) | V4 (Jan-Feb) | V4 (Oct-Feb) |")
    lines.append("|--------|-----------------|-----------------|----------|--------------|--------------|")
    lines.append(f"| **Total P&L** | -$17,885 | -$8,938 | +$566 | +$5,402 | **${stats['total_pnl']:+,.0f}** |")
    lines.append(f"| Total Sims | 51 | 161 | 26 | 63 | {total} |")
    lines.append(f"| Active Trades | 9 | 25 | 20 | 10 | {active} |")
    lines.append(f"| Win Rate | 17.6% | 4.3% | 34.6% | 40.0% | {win_rate:.1f}% |")
    lines.append(f"| Profitable Days | 2/19 | 3/30 | 5/14 | 4/23 | {profitable_days}/{total_days_traded} |")
    lines.append(f"| Cold Market Skips | 0 | 8 | 8 | 8 | {stats['cold_market_days']} |")
    lines.append(f"| Kill Switch | 0 | 2 | 2 | 0 | {stats['kill_switch_days']} |")
    lines.append("")

    # Tier performance
    lines.append("## Tier Performance")
    lines.append("")
    dist = stats['sqs_distribution']
    lines.append("| Tier | Sims | P&L | Avg P&L |")
    lines.append("|------|------|-----|---------|")
    for tier_name, dist_key in [("Shelved (SQS 7-9, $250)", 'shelved'),
                                  ("A-tier (SQS 5-6, $750)", 'a_tier'),
                                  ("B-tier (SQS 4, $250)", 'b_tier')]:
        count = dist[dist_key]
        pnl = stats['tier_pnl'].get(tier_name.split(" ")[0], 0)
        avg = pnl / count if count > 0 else 0
        lines.append(f"| {tier_name} | {count} | ${pnl:+,.0f} | ${avg:+,.0f} |")
    lines.append("")

    # B-tier gate stats
    b_total = dist['b_tier'] + dist['b_gate_skip']
    b_pnl = stats['tier_pnl'].get('B', 0)
    lines.append("## B-Tier Quality Gate Stats")
    lines.append("")
    lines.append(f"- SQS=4 candidates: **{b_total}**")
    lines.append(f"- Passed (gap>=14% AND pm_vol>=10k): **{dist['b_tier']}**")
    lines.append(f"- Blocked: **{dist['b_gate_skip']}**")
    if dist['b_tier'] > 0:
        lines.append(f"- B-tier P&L: **${b_pnl:+,.0f}**")
    lines.append("")

    # SQS distribution
    lines.append("## SQS Distribution")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| Shelved (SQS 7-9) | {dist['shelved']} |")
    lines.append(f"| A-tier (SQS 5-6) | {dist['a_tier']} |")
    lines.append(f"| B-tier (SQS 4, gate passed) | {dist['b_tier']} |")
    lines.append(f"| B-gate skip (SQS 4, gate failed) | {dist['b_gate_skip']} |")
    lines.append(f"| SQS skip (0-3) | {dist['skip']} |")
    lines.append("")

    # Equity curve
    lines.append("## Equity Curve Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Starting Balance | ${equity['starting_balance']:,.0f} |")
    lines.append(f"| Ending Balance | ${equity['ending_balance']:,.0f} |")
    lines.append(f"| Total Return | {equity['total_return_pct']:.1f}% |")
    lines.append(f"| Peak Balance | ${equity['peak_balance']:,.0f} ({equity['peak_date']}) |")
    lines.append(f"| Max Drawdown | ${equity['max_drawdown']:,.0f} ({equity['max_drawdown_pct']:.1f}%) |")
    lines.append(f"| Drawdown Trough | {equity['trough_date']} |")
    lines.append(f"| Longest Winning Streak | {equity['max_winning_streak']} days |")
    lines.append(f"| Longest Losing Streak | {equity['max_losing_streak']} days |")
    lines.append(f"| Buying Power (end) | ${equity['ending_balance'] * 4:,.0f} |")
    lines.append("")

    # Monster trades
    lines.append("## Monster Trades (|P&L| >= $1,000)")
    lines.append("")
    if monsters:
        lines.append("| Date | Symbol | Tier | Risk | P&L |")
        lines.append("|------|--------|------|------|-----|")
        for m in monsters:
            lines.append(f"| {m['date']} | {m['symbol']} | {m['tier']} (SQS={m['sqs']}) | ${m['risk']} | ${m['pnl']:+,.0f} |")
        lines.append("")
        pos_monsters = [m for m in monsters if m['pnl'] > 0]
        neg_monsters = [m for m in monsters if m['pnl'] < 0]
        lines.append(f"- Monster winners: **{len(pos_monsters)}** (total: ${sum(m['pnl'] for m in pos_monsters):+,.0f})")
        lines.append(f"- Monster losers: **{len(neg_monsters)}** (total: ${sum(m['pnl'] for m in neg_monsters):+,.0f})")
        if len(pos_monsters) > 1:
            lines.append(f"- GWAV is **NOT** an anomaly — {len(pos_monsters)} monster winners found")
        elif len(pos_monsters) == 1:
            lines.append(f"- GWAV **IS** the only monster winner across 5 months")
    else:
        lines.append("No trades with |P&L| >= $1,000")
    lines.append("")

    # Kill switch analysis
    lines.append("## Kill Switch Analysis")
    lines.append("")
    kill_switch_found = False
    for date in sorted(stats['session_details'].keys()):
        details = stats['session_details'][date]
        if details['stopped']:
            kill_switch_found = True
            lines.append(f"- **{date}**: {details['stop_reason']}")
            sims_str = ", ".join(f"{s} ${p:+,.0f}" for s, p in details['sims'])
            lines.append(f"  - Sims before stop: {sims_str}")
    if not kill_switch_found:
        lines.append("No kill switch activations across entire test period.")
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
    lines.append("")

    report = "\n".join(lines)

    with open('scanner_results/OCT_FEB_BACKTEST_REPORT_V4.md', 'w') as f:
        f.write(report)
    print(f"\nReport saved to scanner_results/OCT_FEB_BACKTEST_REPORT_V4.md")

    return report


def main():
    print("=" * 60)
    print("  EXTENDED BACKTEST V4 — OCT 2025 to FEB 2026")
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

    # Process Oct-Dec dates
    for date in OCT_DEC_DATES:
        print(f"\n{'=' * 42}")
        print(f"Processing {date}")
        print(f"{'=' * 42}")
        process_date(date, stats)

    # Print Oct-Dec summary before merging
    oct_dec_pnl = stats['total_pnl']
    oct_dec_sims = stats['total_sims']
    print(f"\n{'=' * 60}")
    print(f"  OCT-DEC SUBTOTAL: ${oct_dec_pnl:+,.0f} ({oct_dec_sims} sims)")
    print(f"{'=' * 60}")

    # Merge Jan-Feb results
    print(f"\nMerging Jan-Feb V4 results...")
    merge_jan_feb(stats)

    # Compute equity curve (needs all dates merged)
    equity = compute_equity_curve(stats)
    monthly = compute_monthly_breakdown(stats)
    monsters = find_monster_trades(stats)

    # Final summary
    total = stats['total_sims']
    active = stats['winners'] + stats['losers']
    win_rate = (stats['winners'] / active * 100) if active > 0 else 0
    profitable_days = sum(1 for p in stats['day_pnl'].values() if p > 0)
    total_days_traded = len(stats['day_pnl'])

    print(f"\n{'=' * 60}")
    print(f"  UNIFIED BACKTEST V4 SUMMARY (Oct 2025 – Feb 2026)")
    print(f"{'=' * 60}")
    print(f"  Total P&L:         ${stats['total_pnl']:+,.0f}")
    print(f"  Oct-Dec P&L:       ${oct_dec_pnl:+,.0f}")
    print(f"  Jan-Feb P&L:       $+5,402")
    print(f"  Total Sims:        {total}")
    print(f"  Active Trades:     {active}")
    print(f"  Winners:           {stats['winners']}")
    print(f"  Losers:            {stats['losers']}")
    print(f"  Win Rate (active): {win_rate:.1f}%")
    print(f"  Profitable Days:   {profitable_days}/{total_days_traded}")
    print(f"  Cold Market Skips: {stats['cold_market_days']}")
    print(f"  Kill Switch Fires: {stats['kill_switch_days']}")
    print()
    print(f"  Equity Curve:")
    print(f"    Start:    ${equity['starting_balance']:,.0f}")
    print(f"    End:      ${equity['ending_balance']:,.0f}")
    print(f"    Return:   {equity['total_return_pct']:.1f}%")
    print(f"    Peak:     ${equity['peak_balance']:,.0f} ({equity['peak_date']})")
    print(f"    Drawdown: ${equity['max_drawdown']:,.0f} ({equity['max_drawdown_pct']:.1f}%)")
    print()
    print(f"  Monster Trades: {len(monsters)}")
    for m in monsters:
        print(f"    {m['date']} {m['symbol']} ${m['pnl']:+,.0f} ({m['tier']})")
    print()

    # Save stats JSON
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
        'sqs_distribution': stats['sqs_distribution'],
        'tier_pnl': stats['tier_pnl'],
        'monthly_breakdown': {
            mk: {
                'pnl': m['pnl'],
                'sims': m['sims'],
                'active': m.get('active', 0),
                'winners': m['winners'],
                'losers': m['losers'],
                'days_traded': m.get('days_traded', 0),
                'profitable_days': m.get('profitable_days', 0),
            }
            for mk, m in monthly.items()
        },
        'equity_curve': equity,
        'monster_trades': monsters,
    }

    with open('scanner_results/oct_feb_v4_stats.json', 'w') as f:
        json.dump(report_data, f, indent=2)
    print(f"Stats saved to scanner_results/oct_feb_v4_stats.json")

    # Generate report
    generate_unified_report(stats, equity, monthly, monsters)


if __name__ == "__main__":
    main()
