#!/usr/bin/env python3
"""
V5 Exit Optimization Backtest — 4 passes over Oct 2025–Feb 2026

Pass 1: Baseline (V4 defaults — confirm existing numbers)
Pass 2: Phase 1 only (Smart BE suppression)
Pass 3: Phase 1+2 (add loss cutting)
Pass 4: Full V5 (add dynamic sizing)

Uses existing scanner JSONs and re-runs simulate.py with env var overrides.
"""

import json
import math
import os
import re
import subprocess
import sys
from collections import defaultdict

# ─── Date lists (from run_backtest_v4_extended.py) ───
OCT_DEC_DATES = [
    "2025-10-01", "2025-10-02", "2025-10-03",
    "2025-10-06", "2025-10-07", "2025-10-08", "2025-10-09", "2025-10-10",
    "2025-10-13", "2025-10-14", "2025-10-15", "2025-10-16", "2025-10-17",
    "2025-10-20", "2025-10-21", "2025-10-22", "2025-10-23", "2025-10-24",
    "2025-10-27", "2025-10-28", "2025-10-29", "2025-10-30", "2025-10-31",
    "2025-11-03", "2025-11-04", "2025-11-05", "2025-11-06", "2025-11-07",
    "2025-11-10", "2025-11-11", "2025-11-12", "2025-11-13", "2025-11-14",
    "2025-11-17", "2025-11-18", "2025-11-19", "2025-11-20", "2025-11-21",
    "2025-11-24", "2025-11-25", "2025-11-26",
    "2025-11-28",
    "2025-12-01", "2025-12-02", "2025-12-03", "2025-12-04", "2025-12-05",
    "2025-12-08", "2025-12-09", "2025-12-10", "2025-12-11", "2025-12-12",
    "2025-12-15", "2025-12-16", "2025-12-17", "2025-12-18", "2025-12-19",
    "2025-12-22", "2025-12-23", "2025-12-24",
    "2025-12-26",
    "2025-12-29", "2025-12-30", "2025-12-31",
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

ALL_DATES = OCT_DEC_DATES + JAN_FEB_DATES
MIN_PM_VOLUME = 1000

# ─── V5 env var profiles ───
PASS_CONFIGS = {
    "baseline": {
        "label": "V4 Baseline",
        "env": {},  # No overrides — use V4 defaults
    },
    "phase1": {
        "label": "Phase 1 (Smart BE)",
        "env": {
            "WB_BE_PROFIT_GATE_SIGNAL": "1",
            "WB_BE_NEW_HIGH_GRACE_SEC": "60",
            "WB_BE_GRACE_MIN": "1",
        },
    },
    "phase12": {
        "label": "Phase 1+2 (BE + Loss Cut)",
        "env": {
            "WB_BE_PROFIT_GATE_SIGNAL": "1",
            "WB_BE_NEW_HIGH_GRACE_SEC": "60",
            "WB_BE_GRACE_MIN": "1",
            "WB_MAX_LOSS_R": "1.5",
            "WB_TIME_TIGHTEN_ENABLED": "1",
            "WB_TIME_TIGHTEN_SEC": "120",
            "WB_TIME_TIGHTEN_R": "0.5",
        },
    },
    "full": {
        "label": "Full V5 (BE + Loss Cut + Dynamic Size)",
        "env": {
            "WB_BE_PROFIT_GATE_SIGNAL": "1",
            "WB_BE_NEW_HIGH_GRACE_SEC": "60",
            "WB_BE_GRACE_MIN": "1",
            "WB_MAX_LOSS_R": "1.5",
            "WB_TIME_TIGHTEN_ENABLED": "1",
            "WB_TIME_TIGHTEN_SEC": "120",
            "WB_TIME_TIGHTEN_R": "0.5",
            "WB_DYNAMIC_RISK_ENABLED": "0",  # handled via --risk in orchestrator
        },
    },
}


def compute_sqs(candidate: dict) -> tuple[int, str, int]:
    """V4 tier mapping."""
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


def is_cold_market(candidates: list[dict]) -> bool:
    a_candidates = [c for c in candidates if c.get('profile') == 'A']
    quality_a = [c for c in a_candidates
                 if c['gap_pct'] >= 20 and c.get('pm_volume', 0) >= 5000]
    big_gappers = [c for c in candidates if c['gap_pct'] >= 30]
    return not quality_a or not big_gappers


def parse_pnl_from_output(output: str) -> float:
    match = re.search(r'Gross P&L:\s*\$([+-]?[\d,]+)', output)
    if match:
        return float(match.group(1).replace(',', ''))
    return 0.0


def parse_be_exits_from_output(output: str) -> list[float]:
    """Extract P&L of individual trades that exited via bearish_engulfing."""
    be_pnls = []
    # Look for exit reason lines
    for match in re.finditer(r'EXIT.*bearish_engulfing.*P&L.*\$([+-]?[\d,.]+)', output):
        try:
            be_pnls.append(float(match.group(1).replace(',', '')))
        except ValueError:
            pass
    return be_pnls


def get_sim_tasks(pass_name: str) -> list[dict]:
    """Build list of (date, symbol, profile, tier, risk, sim_start) from scanner JSONs."""
    from session_manager import SessionManager
    tasks = []

    for date in ALL_DATES:
        json_path = f"scanner_results/{date}.json"
        if not os.path.exists(json_path):
            continue

        with open(json_path) as f:
            candidates = json.load(f)

        if is_cold_market(candidates):
            continue

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
                continue

            if p == 'A' and 0.5 <= flt <= 5.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 40.0:
                profile_a.append(c)
            elif p == 'B' and 5.0 <= flt <= 10.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 25.0:
                profile_b.append(c)

        profile_a.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
        profile_b.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
        profile_b = profile_b[:2]

        session = SessionManager()
        all_candidates = profile_a + profile_b

        for c in all_candidates:
            sym = c['symbol']
            profile = c['profile']
            sim_start = c.get('sim_start', '07:00')
            sqs, tier, risk = compute_sqs(c)

            if risk == 0:
                continue

            # B-tier quality gate
            if tier == "B":
                pm_vol = c.get('pm_volume', 0) or 0
                gap = c.get('gap_pct', 0) or 0
                if gap < 14.0 or pm_vol < 10_000:
                    continue

            # Kill switch check
            if session.should_stop():
                break

            tasks.append({
                'date': date,
                'symbol': sym,
                'profile': profile,
                'tier': tier,
                'risk': risk,
                'sqs': sqs,
                'sim_start': sim_start,
            })

            # Record a placeholder to keep session manager in sync
            # (we'll get actual P&L during the run)

    return tasks


def run_sim(task: dict, env_overrides: dict, output_dir: str, equity: float = None) -> dict:
    """Run a single simulate.py invocation with env overrides."""
    date = task['date']
    sym = task['symbol']
    profile = task['profile']
    risk = task['risk']
    tier = task['tier']
    sqs = task['sqs']
    sim_start = task['sim_start']

    # For full V5, compute dynamic risk based on current equity
    if equity is not None:
        risk_pct = 2.5
        min_risk = 250
        max_risk = 1500
        dynamic_risk = equity * (risk_pct / 100.0)
        # Scale proportionally: A-tier base is 750, B/Shelved is 250
        # If base equity = 30000, base A-tier risk = 750 (2.5%)
        # Dynamic scales the base risk by equity ratio
        equity_ratio = equity / 30000.0
        risk = max(min_risk, min(max_risk, int(risk * equity_ratio)))

    outfile = f"{output_dir}/{date}_{sym}.txt"

    # Build env
    env = os.environ.copy()
    for k, v in env_overrides.items():
        env[k] = v

    if profile == "B":
        cmd = f"timeout 180 python simulate.py {sym} {date} {sim_start} 12:00 --profile B --ticks --feed databento --l2 --no-fundamentals --risk {risk}"
    else:
        cmd = f"timeout 120 python simulate.py {sym} {date} {sim_start} 12:00 --profile A --ticks --no-fundamentals --risk {risk}"

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=200, env=env)
        output = result.stdout + result.stderr

        # Profile B Databento fallback
        if profile == "B" and (result.returncode != 0 or "license_not_found" in output or "403" in output or "Error" in output):
            cmd = f"timeout 120 python simulate.py {sym} {date} {sim_start} 12:00 --profile B --ticks --no-fundamentals --risk {risk}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=140, env=env)
            output = result.stdout + result.stderr

        with open(outfile, 'w') as f:
            f.write(f"# V5 risk={risk} sqs={sqs} tier={tier}\n")
            f.write(output)

        pnl = parse_pnl_from_output(output)
        be_exits = parse_be_exits_from_output(output)

    except subprocess.TimeoutExpired:
        pnl = 0.0
        be_exits = []
        output = ""

    return {
        'date': date,
        'symbol': sym,
        'profile': profile,
        'tier': tier,
        'risk': risk,
        'sqs': sqs,
        'pnl': pnl,
        'be_exits': be_exits,
    }


def run_pass(pass_name: str, config: dict, tasks: list[dict]) -> dict:
    """Run one complete pass over all sim tasks."""
    label = config['label']
    env_overrides = config['env']
    output_dir = f"scanner_results/v5_{pass_name}"
    os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"  PASS: {label}")
    print(f"  Env overrides: {env_overrides or '(none)'}")
    print(f"  Output: {output_dir}/")
    print(f"{'=' * 60}")

    results = []
    equity = 30000.0  # Starting balance for dynamic sizing

    from session_manager import SessionManager

    # Group tasks by date for session management
    tasks_by_date = defaultdict(list)
    for t in tasks:
        tasks_by_date[t['date']].append(t)

    for date in sorted(tasks_by_date.keys()):
        date_tasks = tasks_by_date[date]
        session = SessionManager()
        print(f"\n  --- {date} ({len(date_tasks)} sims) ---")

        for task in date_tasks:
            # Kill switch
            if session.should_stop():
                print(f"  KILL SWITCH: {session.stop_reason}")
                break

            # Check cache
            cached_file = f"{output_dir}/{task['date']}_{task['symbol']}.txt"
            if os.path.exists(cached_file) and os.path.getsize(cached_file) > 0:
                with open(cached_file) as f:
                    existing = f.read()
                if f"risk={task['risk']}" in existing:
                    pnl = parse_pnl_from_output(existing)
                    session.record_sim(task['symbol'], pnl)
                    print(f"  CACHED {task['symbol']} SQS={task['sqs']}({task['tier']}) ${task['risk']} P&L=${pnl:+,.0f}")
                    results.append({
                        'date': task['date'], 'symbol': task['symbol'],
                        'profile': task['profile'], 'tier': task['tier'],
                        'risk': task['risk'], 'sqs': task['sqs'],
                        'pnl': pnl, 'be_exits': [],
                    })
                    if pass_name == "full":
                        equity += pnl
                    continue

            eq = equity if pass_name == "full" else None
            print(f"  RUN  {task['symbol']} {task['profile']} SQS={task['sqs']}({task['tier']}) ${task['risk']}", end="", flush=True)
            r = run_sim(task, env_overrides, output_dir, equity=eq)
            results.append(r)
            session.record_sim(task['symbol'], r['pnl'])
            print(f" → ${r['pnl']:+,.0f}")

            if pass_name == "full":
                equity += r['pnl']

        print(f"  SESSION [{date}]: {session.summary()}")

    return {
        'pass_name': pass_name,
        'label': label,
        'results': results,
        'final_equity': equity if pass_name == "full" else None,
    }


def analyze_pass(pass_data: dict) -> dict:
    """Compute summary metrics for a completed pass."""
    results = pass_data['results']

    total_pnl = sum(r['pnl'] for r in results)
    active = [r for r in results if r['pnl'] != 0]
    winners = [r for r in results if r['pnl'] > 0]
    losers = [r for r in results if r['pnl'] < 0]

    # Monster trades (|P&L| >= $1000)
    monsters = [r for r in results if abs(r['pnl']) >= 1000]
    monster_pnl = sum(r['pnl'] for r in monsters)

    # Non-monster trades
    non_monsters = [r for r in active if abs(r['pnl']) < 1000]
    non_monster_pnl = sum(r['pnl'] for r in non_monsters)
    non_monster_avg = non_monster_pnl / len(non_monsters) if non_monsters else 0

    # Non-monster wins/losses
    nm_winners = [r for r in non_monsters if r['pnl'] > 0]
    nm_losers = [r for r in non_monsters if r['pnl'] < 0]
    nm_avg_win = sum(r['pnl'] for r in nm_winners) / len(nm_winners) if nm_winners else 0
    nm_avg_loss = sum(r['pnl'] for r in nm_losers) / len(nm_losers) if nm_losers else 0

    # Without GWAV
    gwav_pnl = sum(r['pnl'] for r in results if r['symbol'] == 'GWAV')
    without_gwav = total_pnl - gwav_pnl

    # Tier breakdown
    tier_pnl = defaultdict(float)
    tier_count = defaultdict(int)
    for r in results:
        tier_pnl[r['tier']] += r['pnl']
        tier_count[r['tier']] += 1

    # Monthly breakdown
    monthly = defaultdict(lambda: {'pnl': 0, 'sims': 0, 'winners': 0, 'losers': 0})
    for r in results:
        mk = r['date'][:7]
        monthly[mk]['sims'] += 1
        monthly[mk]['pnl'] += r['pnl']
        if r['pnl'] > 0:
            monthly[mk]['winners'] += 1
        elif r['pnl'] < 0:
            monthly[mk]['losers'] += 1

    # Day P&L
    day_pnl = defaultdict(float)
    for r in results:
        day_pnl[r['date']] += r['pnl']

    # Equity curve
    balance = 30000.0
    peak_balance = 30000.0
    max_drawdown = 0
    for date in sorted(set(ALL_DATES)):
        dp = day_pnl.get(date, 0)
        balance += dp
        if balance > peak_balance:
            peak_balance = balance
        dd = peak_balance - balance
        if dd > max_drawdown:
            max_drawdown = dd

    return {
        'label': pass_data['label'],
        'total_pnl': total_pnl,
        'total_sims': len(results),
        'active_trades': len(active),
        'winners': len(winners),
        'losers': len(losers),
        'win_rate': len(winners) / len(active) * 100 if active else 0,
        'monster_pnl': monster_pnl,
        'monster_count': len(monsters),
        'monsters': sorted(monsters, key=lambda x: x['pnl'], reverse=True),
        'non_monster_pnl': non_monster_pnl,
        'non_monster_count': len(non_monsters),
        'non_monster_avg': non_monster_avg,
        'nm_avg_win': nm_avg_win,
        'nm_avg_loss': nm_avg_loss,
        'without_gwav': without_gwav,
        'gwav_pnl': gwav_pnl,
        'tier_pnl': dict(tier_pnl),
        'tier_count': dict(tier_count),
        'monthly': dict(monthly),
        'day_pnl': dict(day_pnl),
        'ending_balance': balance,
        'peak_balance': peak_balance,
        'max_drawdown': max_drawdown,
        'final_equity': pass_data.get('final_equity'),
    }


def generate_report(pass_name: str, metrics: dict, output_path: str):
    """Generate markdown report for a single pass."""
    m = metrics
    lines = []
    lines.append(f"# V5 Backtest Report — {m['label']}")
    lines.append("")
    lines.append(f"**Generated:** 2026-03-09")
    lines.append(f"**Window:** Oct 2025 – Feb 2026")
    lines.append(f"**Pass:** {pass_name}")
    lines.append("")

    # Headline
    lines.append("## Headline Metrics")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Total P&L** | **${m['total_pnl']:+,.0f}** |")
    lines.append(f"| Total Sims | {m['total_sims']} |")
    lines.append(f"| Active Trades | {m['active_trades']} |")
    lines.append(f"| Winners / Losers | {m['winners']} / {m['losers']} |")
    lines.append(f"| Win Rate | {m['win_rate']:.1f}% |")
    lines.append(f"| Without GWAV | ${m['without_gwav']:+,.0f} |")
    lines.append(f"| GWAV P&L | ${m['gwav_pnl']:+,.0f} |")
    lines.append("")

    # Non-monster analysis
    lines.append("## Non-Monster Trade Analysis (|P&L| < $1,000)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Count | {m['non_monster_count']} |")
    lines.append(f"| Total P&L | ${m['non_monster_pnl']:+,.0f} |")
    lines.append(f"| Avg P&L/trade | ${m['non_monster_avg']:+,.0f} |")
    lines.append(f"| Avg Win | ${m['nm_avg_win']:+,.0f} |")
    lines.append(f"| Avg Loss | ${m['nm_avg_loss']:+,.0f} |")
    lines.append("")

    # Monster trades
    lines.append("## Monster Trades (|P&L| >= $1,000)")
    lines.append("")
    if m['monsters']:
        lines.append("| Date | Symbol | Tier | Risk | P&L |")
        lines.append("|------|--------|------|------|-----|")
        for mon in m['monsters']:
            lines.append(f"| {mon['date']} | {mon['symbol']} | {mon['tier']} | ${mon['risk']} | ${mon['pnl']:+,.0f} |")
        lines.append("")
        lines.append(f"Monster total: ${m['monster_pnl']:+,.0f}")
    else:
        lines.append("No monster trades.")
    lines.append("")

    # Tier breakdown
    lines.append("## Tier Performance")
    lines.append("")
    lines.append("| Tier | Sims | P&L | Avg |")
    lines.append("|------|------|-----|-----|")
    for tier in ["A", "B", "Shelved"]:
        cnt = m['tier_count'].get(tier, 0)
        pnl = m['tier_pnl'].get(tier, 0)
        avg = pnl / cnt if cnt > 0 else 0
        lines.append(f"| {tier} | {cnt} | ${pnl:+,.0f} | ${avg:+,.0f} |")
    lines.append("")

    # Monthly breakdown
    lines.append("## Monthly Breakdown")
    lines.append("")
    lines.append("| Month | Sims | W/L | P&L |")
    lines.append("|-------|------|-----|-----|")
    for mk in ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]:
        mo = m['monthly'].get(mk, {'sims': 0, 'winners': 0, 'losers': 0, 'pnl': 0})
        lines.append(f"| {mk} | {mo['sims']} | {mo['winners']}/{mo['losers']} | ${mo['pnl']:+,.0f} |")
    lines.append("")

    # Equity curve
    lines.append("## Equity Curve")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Starting | $30,000 |")
    lines.append(f"| Ending | ${m['ending_balance']:,.0f} |")
    lines.append(f"| Peak | ${m['peak_balance']:,.0f} |")
    lines.append(f"| Max Drawdown | ${m['max_drawdown']:,.0f} |")
    if m['final_equity'] is not None:
        lines.append(f"| Dynamic Equity (end) | ${m['final_equity']:,.0f} |")
    lines.append("")

    report = "\n".join(lines)
    with open(output_path, 'w') as f:
        f.write(report)
    print(f"Report saved: {output_path}")
    return report


def generate_comparison_report(all_metrics: dict):
    """Generate a comparison report across all passes."""
    lines = []
    lines.append("# V5 Exit Optimization — Cross-Pass Comparison")
    lines.append("")
    lines.append("**Generated:** 2026-03-09")
    lines.append("**Window:** Oct 2025 – Feb 2026 (102 trading days)")
    lines.append("")

    # Main comparison table
    lines.append("## Summary Comparison")
    lines.append("")
    header = "| Metric |"
    sep = "|--------|"
    for pn in ["baseline", "phase1", "phase12", "full"]:
        m = all_metrics.get(pn)
        if m:
            header += f" {m['label']} |"
            sep += "------|"
    lines.append(header)
    lines.append(sep)

    def row(label, key, fmt="$"):
        r = f"| {label} |"
        for pn in ["baseline", "phase1", "phase12", "full"]:
            m = all_metrics.get(pn)
            if m:
                v = m.get(key, 0)
                if fmt == "$":
                    r += f" ${v:+,.0f} |"
                elif fmt == "%":
                    r += f" {v:.1f}% |"
                elif fmt == "n":
                    r += f" {v} |"
                else:
                    r += f" {v} |"
        return r

    lines.append(row("**Total P&L**", "total_pnl"))
    lines.append(row("Active Trades", "active_trades", "n"))
    lines.append(row("Win Rate", "win_rate", "%"))
    lines.append(row("Without GWAV", "without_gwav"))
    lines.append(row("Non-monster avg", "non_monster_avg"))
    lines.append(row("Avg Win (non-monster)", "nm_avg_win"))
    lines.append(row("Avg Loss (non-monster)", "nm_avg_loss"))
    lines.append(row("Monster P&L", "monster_pnl"))
    lines.append(row("Max Drawdown", "max_drawdown"))
    lines.append(row("Ending Balance", "ending_balance"))
    lines.append("")

    # Monster trade comparison
    lines.append("## Monster Trade Comparison")
    lines.append("")
    lines.append("| Symbol |")
    for pn in ["baseline", "phase1", "phase12", "full"]:
        m = all_metrics.get(pn)
        if m:
            lines[-1] = lines[-1][:-1] + f" {m['label']} |"
    lines.append("|--------|" + "------|" * len([p for p in ["baseline", "phase1", "phase12", "full"] if p in all_metrics]))

    # Collect all monster symbols
    all_monster_syms = set()
    for pn in ["baseline", "phase1", "phase12", "full"]:
        m = all_metrics.get(pn)
        if m:
            for mon in m.get('monsters', []):
                all_monster_syms.add((mon['date'], mon['symbol']))

    for date, sym in sorted(all_monster_syms):
        r = f"| {sym} ({date}) |"
        for pn in ["baseline", "phase1", "phase12", "full"]:
            m = all_metrics.get(pn)
            if m:
                found = [x for x in m.get('monsters', []) if x['symbol'] == sym and x['date'] == date]
                if found:
                    r += f" ${found[0]['pnl']:+,.0f} |"
                else:
                    # Check if it exists as non-monster
                    all_r = [x for x in m.get('_results', []) if x['symbol'] == sym and x['date'] == date]
                    if all_r:
                        r += f" ${all_r[0]['pnl']:+,.0f} |"
                    else:
                        r += " — |"
        lines.append(r)
    lines.append("")

    # Monthly comparison
    lines.append("## Monthly P&L Comparison")
    lines.append("")
    header = "| Month |"
    for pn in ["baseline", "phase1", "phase12", "full"]:
        m = all_metrics.get(pn)
        if m:
            header += f" {m['label']} |"
    lines.append(header)
    lines.append("|-------|" + "------|" * len([p for p in ["baseline", "phase1", "phase12", "full"] if p in all_metrics]))

    for mk in ["2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]:
        r = f"| {mk} |"
        for pn in ["baseline", "phase1", "phase12", "full"]:
            m = all_metrics.get(pn)
            if m:
                mo = m['monthly'].get(mk, {'pnl': 0})
                r += f" ${mo['pnl']:+,.0f} |"
        lines.append(r)
    lines.append("")

    report = "\n".join(lines)
    with open("scanner_results/V5_COMPARISON_REPORT.md", 'w') as f:
        f.write(report)
    print(f"\nComparison report saved: scanner_results/V5_COMPARISON_REPORT.md")


def main():
    # Determine which passes to run
    passes_to_run = sys.argv[1:] if len(sys.argv) > 1 else ["baseline", "phase1", "phase12", "full"]

    print("=" * 60)
    print("  V5 EXIT OPTIMIZATION BACKTEST")
    print(f"  Passes: {', '.join(passes_to_run)}")
    print("=" * 60)

    # Build task list (same for all passes)
    print("\nBuilding sim task list...")
    tasks = get_sim_tasks("baseline")
    print(f"  {len(tasks)} sim tasks across {len(set(t['date'] for t in tasks))} dates")

    all_metrics = {}

    for pass_name in passes_to_run:
        if pass_name not in PASS_CONFIGS:
            print(f"Unknown pass: {pass_name}")
            continue

        config = PASS_CONFIGS[pass_name]
        pass_data = run_pass(pass_name, config, tasks)
        metrics = analyze_pass(pass_data)
        metrics['_results'] = pass_data['results']  # Keep for comparison report

        # Generate individual report
        report_name = {
            "baseline": "V5_BASELINE_REPORT.md",
            "phase1": "V5_PHASE1_REPORT.md",
            "phase12": "V5_PHASE12_REPORT.md",
            "full": "V5_FULL_REPORT.md",
        }[pass_name]
        generate_report(pass_name, metrics, f"scanner_results/{report_name}")

        all_metrics[pass_name] = metrics

        # Print summary
        print(f"\n  {metrics['label']}: ${metrics['total_pnl']:+,.0f} "
              f"({metrics['winners']}W/{metrics['losers']}L, {metrics['win_rate']:.1f}% WR) "
              f"without-GWAV=${metrics['without_gwav']:+,.0f} "
              f"non-monster-avg=${metrics['non_monster_avg']:+,.0f}")

    # Generate comparison report if we ran multiple passes
    if len(all_metrics) > 1:
        generate_comparison_report(all_metrics)

    print("\n" + "=" * 60)
    print("  V5 BACKTEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
