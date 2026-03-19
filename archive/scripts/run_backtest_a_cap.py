#!/usr/bin/env python3
"""
Profile A Risk Cap Backtest — $750 → $500

Same V6.2 wide-B system but with Profile A capped at $500 risk.
Compares against $750 baseline from v6_wide_b run.
Output saved to scanner_results/v6_a_cap/ for isolation.
"""

import json
import os
import re
import subprocess
import sys

from session_manager import SessionManager

# Jan-Aug 2025 trading days
JAN_AUG_DATES = [
    "2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08",
    "2025-01-10", "2025-01-13", "2025-01-14", "2025-01-15", "2025-01-16",
    "2025-01-17", "2025-01-21", "2025-01-22", "2025-01-23", "2025-01-24",
    "2025-01-27", "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",
    "2025-02-03", "2025-02-04", "2025-02-05", "2025-02-06", "2025-02-07",
    "2025-02-10", "2025-02-11", "2025-02-12", "2025-02-13", "2025-02-14",
    "2025-02-18", "2025-02-19", "2025-02-20", "2025-02-21",
    "2025-02-24", "2025-02-25", "2025-02-26", "2025-02-27", "2025-02-28",
    "2025-03-03", "2025-03-04", "2025-03-05", "2025-03-06", "2025-03-07",
    "2025-03-10", "2025-03-11", "2025-03-12", "2025-03-13", "2025-03-14",
    "2025-03-17", "2025-03-18", "2025-03-19", "2025-03-20", "2025-03-21",
    "2025-03-24", "2025-03-25", "2025-03-26", "2025-03-27", "2025-03-28",
    "2025-03-31",
    "2025-04-01", "2025-04-02", "2025-04-03", "2025-04-04",
    "2025-04-07", "2025-04-08", "2025-04-09", "2025-04-10", "2025-04-11",
    "2025-04-14", "2025-04-15", "2025-04-16", "2025-04-17",
    "2025-04-21", "2025-04-22", "2025-04-23", "2025-04-24", "2025-04-25",
    "2025-04-28", "2025-04-29", "2025-04-30",
    "2025-05-01", "2025-05-02",
    "2025-05-05", "2025-05-06", "2025-05-07", "2025-05-08", "2025-05-09",
    "2025-05-12", "2025-05-13", "2025-05-14", "2025-05-15", "2025-05-16",
    "2025-05-19", "2025-05-20", "2025-05-21", "2025-05-22", "2025-05-23",
    "2025-05-27", "2025-05-28", "2025-05-29", "2025-05-30",
    "2025-06-02", "2025-06-03", "2025-06-04", "2025-06-05", "2025-06-06",
    "2025-06-09", "2025-06-10", "2025-06-11", "2025-06-12", "2025-06-13",
    "2025-06-16", "2025-06-17", "2025-06-18", "2025-06-20",
    "2025-06-23", "2025-06-24", "2025-06-25", "2025-06-26", "2025-06-27",
    "2025-06-30",
    "2025-07-01", "2025-07-02", "2025-07-03",
    "2025-07-07", "2025-07-08", "2025-07-09", "2025-07-10", "2025-07-11",
    "2025-07-14", "2025-07-15", "2025-07-16", "2025-07-17", "2025-07-18",
    "2025-07-21", "2025-07-22", "2025-07-23", "2025-07-24", "2025-07-25",
    "2025-07-28", "2025-07-29", "2025-07-30", "2025-07-31",
    "2025-08-01",
    "2025-08-04", "2025-08-05", "2025-08-06", "2025-08-07", "2025-08-08",
    "2025-08-11", "2025-08-12", "2025-08-14", "2025-08-15",
    "2025-08-18", "2025-08-19", "2025-08-20", "2025-08-21",
]

# Oct 2025-Feb 2026 trading days
OCT_FEB_DATES = [
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
    "2026-01-02", "2026-01-03", "2026-01-05", "2026-01-06", "2026-01-07",
    "2026-01-08", "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14",
    "2026-01-15", "2026-01-16", "2026-01-21", "2026-01-22", "2026-01-23",
    "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29",
    "2026-02-02", "2026-02-03", "2026-02-04", "2026-02-05", "2026-02-06",
    "2026-02-09", "2026-02-10", "2026-02-11", "2026-02-12", "2026-02-13",
    "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20", "2026-02-23",
    "2026-02-24", "2026-02-25", "2026-02-26", "2026-02-27",
]

ALL_DATES = JAN_AUG_DATES + OCT_FEB_DATES

OUTPUT_DIR = "scanner_results/v6_a_cap"
MIN_PM_VOLUME = 1000

# ── WIDE B FILTER PARAMS (unchanged from v6_wide_b) ──
B_FLOAT_MIN = 5.0
B_FLOAT_MAX = 15.0
B_GAP_MIN = 10.0
B_GAP_MAX = 35.0
B_MAX_PER_DAY = 3
B_GATE_GAP_MIN = 12.0
B_GATE_VOL_MIN = 5_000


def compute_sqs(candidate: dict) -> tuple[int, str, int]:
    """V4 tier mapping with Profile A risk cap at $500."""
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
        return sqs, "A", 500      # <-- Capped at $500 (was $750)
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
            elif p == 'B' and B_FLOAT_MIN <= flt <= B_FLOAT_MAX and 3.0 <= price <= 10.0 and B_GAP_MIN <= gap <= B_GAP_MAX and pmv >= MIN_PM_VOLUME:
                would_trade.append(f"{c['symbol']}:B")
        if would_trade:
            print(f"  Would-have-traded: {', '.join(would_trade)} ({len(would_trade)} candidates skipped)")
        return

    # Filter candidates — Profile A unchanged, Profile B WIDENED
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
        elif p == 'B' and B_FLOAT_MIN <= flt <= B_FLOAT_MAX and 3.0 <= price <= 10.0 and B_GAP_MIN <= gap <= B_GAP_MAX:
            profile_b.append(c)
        elif p == 'B' and flt is not None and flt > B_FLOAT_MAX:
            stats['float_filtered'] += 1

    profile_a.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
    profile_b.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
    profile_b = profile_b[:B_MAX_PER_DAY]

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

        # V6.2: Profile B risk cap — $250 max regardless of SQS
        if profile == 'B' and risk > 250:
            risk = 250

        if risk == 0:
            stats['sqs_skipped'] += 1
            stats['sqs_distribution']['skip'] += 1
            print(f"  SQS SKIP {sym} (SQS={sqs})")
            continue

        # B-tier quality gate — WIDENED thresholds
        if tier == "B":
            pm_vol = c.get('pm_volume', 0) or 0
            gap = c.get('gap_pct', 0) or 0
            if gap < B_GATE_GAP_MIN or pm_vol < B_GATE_VOL_MIN:
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

        outfile = f"{OUTPUT_DIR}/{date}_{sym}.txt"

        # Resume-safe: skip if already exists with matching risk
        cached = False
        pnl = 0.0
        if os.path.exists(outfile) and os.path.getsize(outfile) > 0:
            with open(outfile) as f:
                existing = f.read()
            if f"risk={risk}" in existing:
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
                    f.write(f"# V6.2-a-cap risk={risk} sqs={sqs} tier={tier}\n")
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
            stats['pnl_wins'].append(pnl)
        elif pnl < 0:
            stats['losers'] += 1
            stats['pnl_losses'].append(pnl)
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


def load_750_baseline() -> dict:
    """Load A@$750 baseline stats from v6_wide_b and earlier runs."""
    baseline = {
        'jan_aug': {'a_sims': [], 'b_sims': []},
        'oct_feb': {'a_sims': [], 'b_sims': []},
    }

    # The wide-B run has both A and B data for the full date range
    wb_path = "scanner_results/v6_wide_b/wide_b_stats.json"
    if os.path.exists(wb_path):
        with open(wb_path) as f:
            wb = json.load(f)
        for d in wb.get('sim_details', []):
            # d = [date, symbol, profile, pnl, sqs, risk, tier]
            date = d[0]
            profile = d[2]
            if date <= "2025-08-31":
                if profile == 'A':
                    baseline['jan_aug']['a_sims'].append(d)
                else:
                    baseline['jan_aug']['b_sims'].append(d)
            else:
                if profile == 'A':
                    baseline['oct_feb']['a_sims'].append(d)
                else:
                    baseline['oct_feb']['b_sims'].append(d)
        return baseline

    # Fallback: load from separate period stats files
    ja_path = "scanner_results/v6_jan_aug/jan_aug_v6_stats.json"
    if os.path.exists(ja_path):
        with open(ja_path) as f:
            ja = json.load(f)
        for d in ja.get('sim_details', []):
            if d[2] == 'A':
                baseline['jan_aug']['a_sims'].append(d)
            else:
                baseline['jan_aug']['b_sims'].append(d)

    of_path = "scanner_results/oct_feb_v4_stats.json"
    if os.path.exists(of_path):
        with open(of_path) as f:
            of = json.load(f)
        for d in of.get('sim_details', []):
            if d[2] == 'A':
                baseline['oct_feb']['a_sims'].append(d)
            else:
                baseline['oct_feb']['b_sims'].append(d)

    return baseline


def get_month_key(date: str) -> str:
    """Extract YYYY-MM from date string."""
    return date[:7]


def compute_profile_stats(sims: list) -> dict:
    """Compute stats for a list of sim detail tuples."""
    active = [x for x in sims if x[3] != 0]
    wins = [x for x in sims if x[3] > 0]
    losses = [x for x in sims if x[3] < 0]
    total_pnl = sum(x[3] for x in sims)
    wr = (len(wins) / len(active) * 100) if active else 0
    avg_win = (sum(x[3] for x in wins) / len(wins)) if wins else 0
    avg_loss = (sum(x[3] for x in losses) / len(losses)) if losses else 0
    wl_ratio = (avg_win / abs(avg_loss)) if avg_loss != 0 else float('inf')

    # Max drawdown (running P&L)
    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for x in sims:
        running += x[3]
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_dd:
            max_dd = dd

    return {
        'sims': len(sims),
        'active': len(active),
        'winners': len(wins),
        'losers': len(losses),
        'wr': wr,
        'pnl': total_pnl,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'wl_ratio': wl_ratio,
        'max_dd': max_dd,
    }


def generate_report(stats: dict):
    """Generate three-way comparison report: A@$750 vs A@$500 vs B."""
    baseline = load_750_baseline()

    # ── Current run (A@$500) split by profile and period ──
    a500_ja = [x for x in stats['sim_details'] if x[2] == 'A' and x[0] <= "2025-08-31"]
    a500_of = [x for x in stats['sim_details'] if x[2] == 'A' and x[0] > "2025-08-31"]
    a500_all = a500_ja + a500_of

    b_ja = [x for x in stats['sim_details'] if x[2] == 'B' and x[0] <= "2025-08-31"]
    b_of = [x for x in stats['sim_details'] if x[2] == 'B' and x[0] > "2025-08-31"]
    b_all = b_ja + b_of

    # ── Baseline A@$750 ──
    a750_ja = baseline['jan_aug']['a_sims']
    a750_of = baseline['oct_feb']['a_sims']
    a750_all = a750_ja + a750_of

    # ── Baseline B (should be unchanged) ──
    b750_ja = baseline['jan_aug']['b_sims']
    b750_of = baseline['oct_feb']['b_sims']
    b750_all = b750_ja + b750_of

    # Compute stats
    s_a750_all = compute_profile_stats(a750_all)
    s_a500_all = compute_profile_stats(a500_all)
    s_a750_ja = compute_profile_stats(a750_ja)
    s_a500_ja = compute_profile_stats(a500_ja)
    s_a750_of = compute_profile_stats(a750_of)
    s_a500_of = compute_profile_stats(a500_of)
    s_b_all = compute_profile_stats(b_all)
    s_b750_all = compute_profile_stats(b750_all)

    def wl_str(r):
        return f"{r:.2f}:1" if r != float('inf') else "N/A"

    lines = []
    lines.append("# Profile A Risk Cap Results — $750 vs $500")
    lines.append("")
    lines.append(f"**Generated:** 2026-03-10")
    lines.append(f"**Branch:** v6-dynamic-sizing")
    lines.append(f"**Dates:** Jan 2025 – Feb 2026 ({len(ALL_DATES)} trading days)")
    lines.append(f"**Change:** Profile A risk $750 → $500, everything else identical")
    lines.append("")

    # ── 1. Profile A comparison table ──
    lines.append("## 1. Profile A Comparison: $750 vs $500")
    lines.append("")
    lines.append("| Metric | A @ $750 | A @ $500 | Delta |")
    lines.append("|--------|----------|----------|-------|")
    lines.append(f"| Total sims | {s_a750_all['sims']} | {s_a500_all['sims']} | {s_a500_all['sims'] - s_a750_all['sims']:+d} |")
    lines.append(f"| Active trades | {s_a750_all['active']} | {s_a500_all['active']} | {s_a500_all['active'] - s_a750_all['active']:+d} |")
    lines.append(f"| Winners | {s_a750_all['winners']} | {s_a500_all['winners']} | {s_a500_all['winners'] - s_a750_all['winners']:+d} |")
    lines.append(f"| Losers | {s_a750_all['losers']} | {s_a500_all['losers']} | {s_a500_all['losers'] - s_a750_all['losers']:+d} |")
    lines.append(f"| Win rate | {s_a750_all['wr']:.1f}% | {s_a500_all['wr']:.1f}% | {s_a500_all['wr'] - s_a750_all['wr']:+.1f}pp |")
    lines.append(f"| Total P&L | ${s_a750_all['pnl']:+,.0f} | ${s_a500_all['pnl']:+,.0f} | ${s_a500_all['pnl'] - s_a750_all['pnl']:+,.0f} |")
    lines.append(f"| Avg win | ${s_a750_all['avg_win']:+,.0f} | ${s_a500_all['avg_win']:+,.0f} | ${s_a500_all['avg_win'] - s_a750_all['avg_win']:+,.0f} |")
    lines.append(f"| Avg loss | ${s_a750_all['avg_loss']:+,.0f} | ${s_a500_all['avg_loss']:+,.0f} | ${s_a500_all['avg_loss'] - s_a750_all['avg_loss']:+,.0f} |")
    lines.append(f"| W/L ratio | {wl_str(s_a750_all['wl_ratio'])} | {wl_str(s_a500_all['wl_ratio'])} | — |")
    lines.append(f"| Max drawdown | ${s_a750_all['max_dd']:,.0f} | ${s_a500_all['max_dd']:,.0f} | ${s_a500_all['max_dd'] - s_a750_all['max_dd']:+,.0f} |")
    lines.append("")

    # ── 2. Per-period breakdown ──
    lines.append("## 2. Per-Period Breakdown")
    lines.append("")
    lines.append("### Jan-Aug 2025 (Validation Set)")
    lines.append("")
    lines.append("| Metric | A @ $750 | A @ $500 | Delta |")
    lines.append("|--------|----------|----------|-------|")
    lines.append(f"| Sims | {s_a750_ja['sims']} | {s_a500_ja['sims']} | {s_a500_ja['sims'] - s_a750_ja['sims']:+d} |")
    lines.append(f"| Active | {s_a750_ja['active']} | {s_a500_ja['active']} | {s_a500_ja['active'] - s_a750_ja['active']:+d} |")
    lines.append(f"| Win rate | {s_a750_ja['wr']:.1f}% | {s_a500_ja['wr']:.1f}% | {s_a500_ja['wr'] - s_a750_ja['wr']:+.1f}pp |")
    lines.append(f"| P&L | ${s_a750_ja['pnl']:+,.0f} | ${s_a500_ja['pnl']:+,.0f} | ${s_a500_ja['pnl'] - s_a750_ja['pnl']:+,.0f} |")
    lines.append(f"| Avg loss | ${s_a750_ja['avg_loss']:+,.0f} | ${s_a500_ja['avg_loss']:+,.0f} | ${s_a500_ja['avg_loss'] - s_a750_ja['avg_loss']:+,.0f} |")
    lines.append(f"| Max DD | ${s_a750_ja['max_dd']:,.0f} | ${s_a500_ja['max_dd']:,.0f} | ${s_a500_ja['max_dd'] - s_a750_ja['max_dd']:+,.0f} |")
    ja_improvement = 0
    if s_a750_ja['pnl'] < 0 and s_a500_ja['pnl'] > s_a750_ja['pnl']:
        ja_improvement = (1 - s_a500_ja['pnl'] / s_a750_ja['pnl']) * 100
    lines.append(f"| **Loss reduction** | — | — | **{ja_improvement:.0f}%** |")
    lines.append("")

    lines.append("### Oct 2025-Feb 2026 (Training Set)")
    lines.append("")
    lines.append("| Metric | A @ $750 | A @ $500 | Delta |")
    lines.append("|--------|----------|----------|-------|")
    lines.append(f"| Sims | {s_a750_of['sims']} | {s_a500_of['sims']} | {s_a500_of['sims'] - s_a750_of['sims']:+d} |")
    lines.append(f"| Active | {s_a750_of['active']} | {s_a500_of['active']} | {s_a500_of['active'] - s_a750_of['active']:+d} |")
    lines.append(f"| Win rate | {s_a750_of['wr']:.1f}% | {s_a500_of['wr']:.1f}% | {s_a500_of['wr'] - s_a750_of['wr']:+.1f}pp |")
    lines.append(f"| P&L | ${s_a750_of['pnl']:+,.0f} | ${s_a500_of['pnl']:+,.0f} | ${s_a500_of['pnl'] - s_a750_of['pnl']:+,.0f} |")
    lines.append(f"| Max DD | ${s_a750_of['max_dd']:,.0f} | ${s_a500_of['max_dd']:,.0f} | ${s_a500_of['max_dd'] - s_a750_of['max_dd']:+,.0f} |")
    lines.append("")

    # ── 3. Monthly P&L table ──
    lines.append("## 3. Monthly P&L Breakdown")
    lines.append("")

    # Build monthly buckets from baseline and current
    months = ["2025-01", "2025-02", "2025-03", "2025-04", "2025-05", "2025-06",
              "2025-07", "2025-08", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]

    def monthly_pnl(sims, month):
        return sum(x[3] for x in sims if x[0].startswith(month))

    lines.append("| Month | A @ $750 | A @ $500 | B | Combined @ $500 |")
    lines.append("|-------|----------|----------|---|-----------------|")
    worst_month_combined = 0
    for m in months:
        a750_m = monthly_pnl(a750_all, m)
        a500_m = monthly_pnl(a500_all, m)
        b_m = monthly_pnl(b_all, m)
        combined_m = a500_m + b_m
        if combined_m < worst_month_combined:
            worst_month_combined = combined_m
        lines.append(f"| {m} | ${a750_m:+,.0f} | ${a500_m:+,.0f} | ${b_m:+,.0f} | ${combined_m:+,.0f} |")

    # Totals
    a750_total = sum(monthly_pnl(a750_all, m) for m in months)
    a500_total = sum(monthly_pnl(a500_all, m) for m in months)
    b_total = sum(monthly_pnl(b_all, m) for m in months)
    combined_total = a500_total + b_total
    lines.append(f"| **Total** | **${a750_total:+,.0f}** | **${a500_total:+,.0f}** | **${b_total:+,.0f}** | **${combined_total:+,.0f}** |")
    lines.append("")

    # ── 4. Profile B validation ──
    lines.append("## 4. Profile B Validation (MUST BE UNCHANGED)")
    lines.append("")
    lines.append("| Metric | Baseline (wide-B run) | This Run |")
    lines.append("|--------|----------------------|----------|")
    lines.append(f"| B total sims | {s_b750_all['sims']} | {s_b_all['sims']} |")
    lines.append(f"| B active trades | {s_b750_all['active']} | {s_b_all['active']} |")
    lines.append(f"| B winners | {s_b750_all['winners']} | {s_b_all['winners']} |")
    lines.append(f"| B win rate | {s_b750_all['wr']:.1f}% | {s_b_all['wr']:.1f}% |")
    lines.append(f"| B total P&L | ${s_b750_all['pnl']:+,.0f} | ${s_b_all['pnl']:+,.0f} |")
    b_match = abs(s_b_all['pnl'] - s_b750_all['pnl']) < 1.0 and s_b_all['sims'] == s_b750_all['sims']
    lines.append(f"| **Match?** | — | **{'YES' if b_match else 'NO — INVESTIGATE'}** |")
    lines.append("")

    # ── 5. Combined system ──
    lines.append("## 5. Combined System")
    lines.append("")
    old_combined = s_a750_all['pnl'] + s_b750_all['pnl']
    new_combined = s_a500_all['pnl'] + s_b_all['pnl']
    lines.append("| Metric | Old (A@$750 + B) | New (A@$500 + B) | Delta |")
    lines.append("|--------|-----------------|-----------------|-------|")
    lines.append(f"| Combined P&L | ${old_combined:+,.0f} | ${new_combined:+,.0f} | ${new_combined - old_combined:+,.0f} |")
    lines.append(f"| A P&L | ${s_a750_all['pnl']:+,.0f} | ${s_a500_all['pnl']:+,.0f} | ${s_a500_all['pnl'] - s_a750_all['pnl']:+,.0f} |")
    lines.append(f"| B P&L | ${s_b750_all['pnl']:+,.0f} | ${s_b_all['pnl']:+,.0f} | ${s_b_all['pnl'] - s_b750_all['pnl']:+,.0f} |")
    lines.append("")

    # ── 6. Decision assessment ──
    lines.append("## 6. Decision Assessment")
    lines.append("")

    # GREEN criteria from directive
    combined_positive = new_combined > 0
    ja_reduced_30 = ja_improvement >= 30
    of_still_positive = s_a500_of['pnl'] > 0
    no_month_worse_2k = worst_month_combined >= -2000

    lines.append("| Criterion | Threshold | Actual | Pass? |")
    lines.append("|-----------|-----------|--------|-------|")
    lines.append(f"| Combined net positive | > $0 | ${new_combined:+,.0f} | {'PASS' if combined_positive else 'FAIL'} |")
    lines.append(f"| Jan-Aug loss reduced ≥30% | ≥30% | {ja_improvement:.0f}% | {'PASS' if ja_reduced_30 else 'FAIL'} |")
    lines.append(f"| Oct-Feb A still positive | > $0 | ${s_a500_of['pnl']:+,.0f} | {'PASS' if of_still_positive else 'FAIL'} |")
    lines.append(f"| No month worse than -$2K | ≥ -$2,000 | ${worst_month_combined:+,.0f} | {'PASS' if no_month_worse_2k else 'FAIL'} |")
    lines.append("")

    green = combined_positive and ja_reduced_30 and of_still_positive and no_month_worse_2k
    yellow = not green and (s_a500_all['pnl'] > s_a750_all['pnl'])
    red = not green and not yellow

    if green:
        decision = "GREEN"
        decision_text = "Keep $500 cap — all criteria met. Combined system is net positive across 260 days."
    elif yellow:
        decision = "YELLOW"
        decision_text = "Pattern improved but not all criteria met. Consider trying $400 cap next."
    else:
        decision = "RED"
        decision_text = "Risk cap alone isn't enough — cap cuts winners more than it limits losers, or system is worse overall."

    lines.append(f"### Decision: **{decision}**")
    lines.append("")
    lines.append(decision_text)
    lines.append("")

    # ── 7. All A trades detail ──
    lines.append("## 7. All Profile A Trades (@ $500)")
    lines.append("")
    if a500_all:
        lines.append("| Date | Symbol | SQS | Risk | P&L |")
        lines.append("|------|--------|-----|------|-----|")
        for d, s, p, pnl, sqs, r, t in a500_all:
            lines.append(f"| {d} | {s} | {sqs} | ${r} | ${pnl:+,.0f} |")
    lines.append("")

    report = "\n".join(lines)
    report_path = "PROFILE_A_RISK_CAP_RESULTS.md"
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\nReport saved to {report_path}")
    return report


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("  PROFILE A RISK CAP BACKTEST — $750 → $500")
    print(f"  {len(ALL_DATES)} trading days")
    print(f"  A risk: $500 (was $750)")
    print(f"  B filters: float<={B_FLOAT_MAX}M gap<={B_GAP_MAX}% max/day={B_MAX_PER_DAY}")
    print(f"  B-gate: gap>={B_GATE_GAP_MIN}% pm_vol>={B_GATE_VOL_MIN:,}")
    print("=" * 60)

    stats = {
        'total_pnl': 0.0,
        'total_sims': 0,
        'winners': 0,
        'losers': 0,
        'pnl_wins': [],
        'pnl_losses': [],
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

    # Final summary
    total = stats['total_sims']
    active = stats['winners'] + stats['losers']
    win_rate = (stats['winners'] / active * 100) if active > 0 else 0

    a_sims = [x for x in stats['sim_details'] if x[2] == 'A']
    b_sims = [x for x in stats['sim_details'] if x[2] == 'B']
    a_pnl = sum(x[3] for x in a_sims)
    b_pnl = sum(x[3] for x in b_sims)

    print(f"\n{'=' * 60}")
    print(f"  PROFILE A RISK CAP — SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total P&L:         ${stats['total_pnl']:+,.0f}")
    print(f"  Total Sims:        {total}")
    print(f"  Active Trades:     {active}")
    print(f"  Win Rate (active): {win_rate:.1f}%")
    print()
    print(f"  Profile A (@ $500): {len(a_sims)} sims, ${a_pnl:+,.0f}")
    print(f"  Profile B (@ $250): {len(b_sims)} sims, ${b_pnl:+,.0f}")
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
        'day_pnl': stats['day_pnl'],
        'sim_details': stats['sim_details'],
        'sqs_distribution': stats['sqs_distribution'],
        'tier_pnl': stats['tier_pnl'],
    }
    stats_path = f"{OUTPUT_DIR}/a_cap_stats.json"
    with open(stats_path, 'w') as f:
        json.dump(report_data, f, indent=2)
    print(f"Stats saved to {stats_path}")

    # Generate comparison report
    generate_report(stats)


if __name__ == "__main__":
    main()
