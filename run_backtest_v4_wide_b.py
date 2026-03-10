#!/usr/bin/env python3
"""
V6.2 Wide Profile B Backtest — Jan-Aug 2025 + Oct 2025-Feb 2026

Widens Profile B filters vs narrow baseline:
  - Float ceiling: 10M → 15M
  - Gap cap: 25% → 35%
  - Max per day: 2 → 3
  - B-gate: gap>=14%/pm_vol>=10K → gap>=12%/pm_vol>=5K

Profile A filters are UNCHANGED.
Output saved to scanner_results/v6_wide_b/ for isolation.
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

OUTPUT_DIR = "scanner_results/v6_wide_b"
MIN_PM_VOLUME = 1000

# ── WIDE B FILTER PARAMS ──
B_FLOAT_MIN = 5.0
B_FLOAT_MAX = 15.0   # was 10.0
B_GAP_MIN = 10.0
B_GAP_MAX = 35.0     # was 25.0
B_MAX_PER_DAY = 3    # was 2
B_GATE_GAP_MIN = 12.0   # was 14.0
B_GATE_VOL_MIN = 5_000  # was 10_000

# ── NARROW B FILTER PARAMS (for comparison tagging) ──
NARROW_FLOAT_MAX = 10.0
NARROW_GAP_MAX = 25.0
NARROW_MAX_PER_DAY = 2
NARROW_GATE_GAP_MIN = 14.0
NARROW_GATE_VOL_MIN = 10_000


def compute_sqs(candidate: dict) -> tuple[int, str, int]:
    """V4 tier mapping with V6.2 Profile B risk cap."""
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


def would_pass_narrow_b_filter(c: dict) -> bool:
    """Check if candidate would pass the NARROW (old) B filters."""
    flt = c.get('float_millions')
    gap = c['gap_pct']
    price = c['pm_price']
    pmv = c.get('pm_volume', 0)
    if flt is None:
        return False
    return (5.0 <= flt <= NARROW_FLOAT_MAX and
            3.0 <= price <= 10.0 and
            10.0 <= gap <= NARROW_GAP_MAX and
            pmv >= MIN_PM_VOLUME)


def would_pass_narrow_b_gate(c: dict) -> bool:
    """Check if candidate would pass the NARROW (old) B-gate."""
    gap = c.get('gap_pct', 0) or 0
    pm_vol = c.get('pm_volume', 0) or 0
    return gap >= NARROW_GATE_GAP_MIN and pm_vol >= NARROW_GATE_VOL_MIN


def tag_new_b_reason(c: dict, slot_index: int) -> list[str]:
    """Tag why this B trade is new (wouldn't exist in narrow run)."""
    reasons = []
    flt = c.get('float_millions', 0)
    gap = c['gap_pct']
    pm_vol = c.get('pm_volume', 0) or 0

    # Filter-level checks
    if flt > NARROW_FLOAT_MAX:
        reasons.append("FLOAT")
    if gap > NARROW_GAP_MAX:
        reasons.append("GAP")

    # B-gate check (only if it would have passed narrow filter)
    if would_pass_narrow_b_filter(c):
        if not would_pass_narrow_b_gate(c):
            reasons.append("BGATE")

    # Slot check (3rd per day, old limit was 2)
    if slot_index >= NARROW_MAX_PER_DAY:
        reasons.append("SLOT")

    return reasons


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
    profile_b = profile_b[:B_MAX_PER_DAY]  # was [:2]

    all_candidates = profile_a + profile_b

    if not all_candidates:
        print(f"  No candidates passed filters for {date}")
        return

    session = SessionManager()

    # Track B slot index for SLOT tagging
    b_slot_index = 0

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

        # Tag new B trades
        is_new_b = False
        new_b_reasons = []
        if profile == 'B':
            new_b_reasons = tag_new_b_reason(c, b_slot_index)
            is_new_b = len(new_b_reasons) > 0
            b_slot_index += 1

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
                new_str = f" [NEW-B: {'+'.join(new_b_reasons)}]" if is_new_b else ""
                print(f"  CACHED {sym} SQS={sqs}({tier}) risk=${risk}{gate_str}{new_str} (P&L: ${pnl:+,.0f})")
                cached = True

        if not cached:
            pmv = c.get('pm_volume', 0)
            gap = c.get('gap_pct', 0)
            flt = c.get('float_millions', 0)
            gate_str = " [B-GATE: PASS]" if tier == "B" else ""
            new_str = f" [NEW-B: {'+'.join(new_b_reasons)}]" if is_new_b else ""
            print(f"  RUN  {sym} profile={profile} start={sim_start} SQS={sqs}({tier}) risk=${risk} pm_vol={pmv:,.0f} gap={gap:.1f}% float={flt:.2f}M{gate_str}{new_str}")

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
                    f.write(f"# V6.2-wide-B risk={risk} sqs={sqs} tier={tier}\n")
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

        # Track new B trades separately
        if is_new_b:
            stats['new_b_trades'].append({
                'date': date, 'symbol': sym, 'sqs': sqs, 'tier': tier,
                'risk': risk, 'pnl': pnl, 'reasons': new_b_reasons,
                'gap': c.get('gap_pct', 0), 'float': c.get('float_millions', 0),
                'pm_vol': c.get('pm_volume', 0),
            })

    print(f"  SESSION [{date}]: {session.summary()}")
    stats['session_summaries'][date] = session.summary()
    stats['session_details'][date] = {
        'stopped': session.stopped,
        'stop_reason': session.stop_reason,
        'session_pnl': session.session_pnl,
        'peak_pnl': session.peak_pnl,
        'sims': [(s, p) for s, p in session.sim_results],
    }


def load_narrow_baseline() -> dict:
    """Load narrow baseline stats from existing backtest results."""
    baseline = {
        'jan_aug': {'b_sims': [], 'a_sims': []},
        'oct_feb': {'b_sims': [], 'a_sims': []},
    }

    # Jan-Aug narrow results
    ja_path = "scanner_results/v6_jan_aug/jan_aug_v6_stats.json"
    if os.path.exists(ja_path):
        with open(ja_path) as f:
            ja = json.load(f)
        for d in ja.get('sim_details', []):
            if d[2] == 'B':
                baseline['jan_aug']['b_sims'].append(d)
            else:
                baseline['jan_aug']['a_sims'].append(d)

    # Oct-Feb narrow results
    of_path = "scanner_results/oct_feb_v4_stats.json"
    if os.path.exists(of_path):
        with open(of_path) as f:
            of = json.load(f)
        for d in of.get('sim_details', []):
            if d[2] == 'B':
                baseline['oct_feb']['b_sims'].append(d)
            else:
                baseline['oct_feb']['a_sims'].append(d)

    return baseline


def generate_report(stats: dict):
    """Generate narrow vs wide comparison report."""
    baseline = load_narrow_baseline()

    # ── Wide B stats ──
    a_sims = [(d, s, p, pnl, sqs, r, t) for d, s, p, pnl, sqs, r, t in stats['sim_details'] if p == 'A']
    b_sims = [(d, s, p, pnl, sqs, r, t) for d, s, p, pnl, sqs, r, t in stats['sim_details'] if p == 'B']
    b_active = [x for x in b_sims if x[3] != 0]
    b_wins = [x for x in b_sims if x[3] > 0]
    b_losses = [x for x in b_sims if x[3] < 0]
    a_active = [x for x in a_sims if x[3] != 0]
    a_wins = [x for x in a_sims if x[3] > 0]
    a_losses = [x for x in a_sims if x[3] < 0]

    b_total_pnl = sum(x[3] for x in b_sims)
    a_total_pnl = sum(x[3] for x in a_sims)
    b_wr = (len(b_wins) / len(b_active) * 100) if b_active else 0
    b_avg_win = (sum(x[3] for x in b_wins) / len(b_wins)) if b_wins else 0
    b_avg_loss = (sum(x[3] for x in b_losses) / len(b_losses)) if b_losses else 0
    b_wl_ratio = (b_avg_win / abs(b_avg_loss)) if b_avg_loss != 0 else float('inf')

    # ── Narrow B stats ──
    narrow_b_all = baseline['jan_aug']['b_sims'] + baseline['oct_feb']['b_sims']
    narrow_b_active = [x for x in narrow_b_all if x[3] != 0]
    narrow_b_wins = [x for x in narrow_b_all if x[3] > 0]
    narrow_b_losses = [x for x in narrow_b_all if x[3] < 0]
    narrow_b_pnl = sum(x[3] for x in narrow_b_all)
    narrow_b_wr = (len(narrow_b_wins) / len(narrow_b_active) * 100) if narrow_b_active else 0
    narrow_b_avg_win = (sum(x[3] for x in narrow_b_wins) / len(narrow_b_wins)) if narrow_b_wins else 0
    narrow_b_avg_loss = (sum(x[3] for x in narrow_b_losses) / len(narrow_b_losses)) if narrow_b_losses else 0
    narrow_b_wl_ratio = (narrow_b_avg_win / abs(narrow_b_avg_loss)) if narrow_b_avg_loss != 0 else float('inf')

    # ── Narrow A stats (for validation) ──
    narrow_a_all = baseline['jan_aug']['a_sims'] + baseline['oct_feb']['a_sims']
    narrow_a_active = [x for x in narrow_a_all if x[3] != 0]
    narrow_a_wins = [x for x in narrow_a_all if x[3] > 0]
    narrow_a_pnl = sum(x[3] for x in narrow_a_all)
    narrow_a_wr = (len(narrow_a_wins) / len(narrow_a_active) * 100) if narrow_a_active else 0

    a_wr_wide = (len(a_wins) / len(a_active) * 100) if a_active else 0

    # ── Count B scanner funnel for both narrow and wide ──
    narrow_b_scanner = 0
    narrow_b_pass_filter = 0
    wide_b_scanner = 0
    wide_b_pass_filter = 0
    for date in ALL_DATES:
        json_path = f"scanner_results/{date}.json"
        if not os.path.exists(json_path):
            continue
        with open(json_path) as f:
            cands = json.load(f)
        for c in cands:
            if c.get('profile') == 'B' and c.get('float_millions') is not None:
                flt = c['float_millions']
                gap = c['gap_pct']
                price = c['pm_price']
                pmv = c.get('pm_volume', 0)
                # Narrow count
                if 5.0 <= flt <= NARROW_FLOAT_MAX:
                    narrow_b_scanner += 1
                    if 3.0 <= price <= 10.0 and 10.0 <= gap <= NARROW_GAP_MAX and pmv >= MIN_PM_VOLUME:
                        narrow_b_pass_filter += 1
                # Wide count
                if B_FLOAT_MIN <= flt <= B_FLOAT_MAX:
                    wide_b_scanner += 1
                    if 3.0 <= price <= 10.0 and B_GAP_MIN <= gap <= B_GAP_MAX and pmv >= MIN_PM_VOLUME:
                        wide_b_pass_filter += 1

    # ── Worst B loss check ──
    worst_b_loss = min((x[3] for x in b_sims if x[3] < 0), default=0)

    # ── Build report ──
    lines = []
    lines.append("# V6.2 Profile B Wide Filter Results — Narrow vs Wide Comparison")
    lines.append("")
    lines.append(f"**Generated:** 2026-03-10")
    lines.append(f"**Branch:** v6-dynamic-sizing")
    lines.append(f"**Dates:** Jan 2025 – Feb 2026 ({len(ALL_DATES)} trading days)")
    lines.append(f"**Engine:** simulate.py --ticks (tick-by-tick replay)")
    lines.append("")
    lines.append("## Filter Changes")
    lines.append("")
    lines.append("| Parameter | Narrow (Old) | Wide (New) |")
    lines.append("|-----------|-------------|------------|")
    lines.append(f"| Float ceiling | 10M | 15M |")
    lines.append(f"| Gap cap | 25% | 35% |")
    lines.append(f"| Max B per day | 2 | 3 |")
    lines.append(f"| B-gate gap min | 14% | 12% |")
    lines.append(f"| B-gate PM vol min | 10,000 | 5,000 |")
    lines.append(f"| B risk cap | $250 | $250 (unchanged) |")
    lines.append("")

    # ── 1. Funnel comparison ──
    lines.append("## 1. Profile B Funnel Comparison")
    lines.append("")
    lines.append("| Stage | Narrow | Wide | Delta |")
    lines.append("|-------|--------|------|-------|")
    lines.append(f"| Scanner B candidates | {narrow_b_scanner} | {wide_b_scanner} | +{wide_b_scanner - narrow_b_scanner} |")
    lines.append(f"| Pass price+gap+float filter | {narrow_b_pass_filter} | {wide_b_pass_filter} | +{wide_b_pass_filter - narrow_b_pass_filter} |")
    lines.append(f"| Survive SQS + B-gate | {len(narrow_b_all)} | {len(b_sims)} | +{len(b_sims) - len(narrow_b_all)} |")
    lines.append(f"| Active trades (P&L != $0) | {len(narrow_b_active)} | {len(b_active)} | +{len(b_active) - len(narrow_b_active)} |")
    lines.append("")

    # ── 2. Performance comparison ──
    lines.append("## 2. Profile B Performance Comparison")
    lines.append("")
    lines.append("| Metric | Narrow (Baseline) | Wide (New) | Delta |")
    lines.append("|--------|------------------|------------|-------|")
    lines.append(f"| Total sims | {len(narrow_b_all)} | {len(b_sims)} | +{len(b_sims) - len(narrow_b_all)} |")
    lines.append(f"| Active trades | {len(narrow_b_active)} | {len(b_active)} | +{len(b_active) - len(narrow_b_active)} |")
    lines.append(f"| Winners | {len(narrow_b_wins)} | {len(b_wins)} | +{len(b_wins) - len(narrow_b_wins)} |")
    lines.append(f"| Losers | {len(narrow_b_losses)} | {len(b_losses)} | +{len(b_losses) - len(narrow_b_losses)} |")
    lines.append(f"| Win rate | {narrow_b_wr:.1f}% | {b_wr:.1f}% | {b_wr - narrow_b_wr:+.1f}pp |")
    lines.append(f"| Total P&L | ${narrow_b_pnl:+,.0f} | ${b_total_pnl:+,.0f} | ${b_total_pnl - narrow_b_pnl:+,.0f} |")
    lines.append(f"| Avg win | ${narrow_b_avg_win:+,.0f} | ${b_avg_win:+,.0f} | ${b_avg_win - narrow_b_avg_win:+,.0f} |")
    lines.append(f"| Avg loss | ${narrow_b_avg_loss:+,.0f} | ${b_avg_loss:+,.0f} | ${b_avg_loss - narrow_b_avg_loss:+,.0f} |")
    wl_narrow_str = f"{narrow_b_wl_ratio:.2f}:1" if narrow_b_wl_ratio != float('inf') else "N/A"
    wl_wide_str = f"{b_wl_ratio:.2f}:1" if b_wl_ratio != float('inf') else "N/A"
    lines.append(f"| Win/loss ratio | {wl_narrow_str} | {wl_wide_str} | — |")
    lines.append(f"| Worst single loss | — | ${worst_b_loss:+,.0f} | — |")
    lines.append("")

    # ── 3. New B trades only ──
    lines.append("## 3. New Profile B Trades (Not in Narrow Run)")
    lines.append("")
    if stats['new_b_trades']:
        lines.append("| Date | Symbol | SQS | Tier | Risk | P&L | Gap% | Float(M) | PM Vol | Filter Tag |")
        lines.append("|------|--------|-----|------|------|-----|------|----------|--------|------------|")
        for t in stats['new_b_trades']:
            tag = "+".join(t['reasons']) if t['reasons'] else "EXISTING"
            lines.append(f"| {t['date']} | {t['symbol']} | {t['sqs']} | {t['tier']} | ${t['risk']} | ${t['pnl']:+,.0f} | {t['gap']:.1f}% | {t['float']:.1f}M | {t['pm_vol']:,.0f} | {tag} |")
        lines.append("")
        new_active = [t for t in stats['new_b_trades'] if t['pnl'] != 0]
        new_wins = [t for t in stats['new_b_trades'] if t['pnl'] > 0]
        new_losses = [t for t in stats['new_b_trades'] if t['pnl'] < 0]
        new_pnl = sum(t['pnl'] for t in stats['new_b_trades'])
        lines.append(f"**New B trades:** {len(stats['new_b_trades'])} total, {len(new_active)} active, {len(new_wins)}W/{len(new_losses)}L, ${new_pnl:+,.0f}")
        lines.append("")
        # Breakdown by reason
        reason_counts = {}
        for t in stats['new_b_trades']:
            for r in t['reasons']:
                if r not in reason_counts:
                    reason_counts[r] = {'count': 0, 'pnl': 0, 'active': 0}
                reason_counts[r]['count'] += 1
                reason_counts[r]['pnl'] += t['pnl']
                if t['pnl'] != 0:
                    reason_counts[r]['active'] += 1
        lines.append("**Breakdown by filter change:**")
        lines.append("")
        lines.append("| Filter | New Trades | Active | P&L |")
        lines.append("|--------|-----------|--------|-----|")
        for r in ['FLOAT', 'GAP', 'BGATE', 'SLOT']:
            if r in reason_counts:
                rc = reason_counts[r]
                lines.append(f"| {r} | {rc['count']} | {rc['active']} | ${rc['pnl']:+,.0f} |")
            else:
                lines.append(f"| {r} | 0 | 0 | $0 |")
        lines.append("")
    else:
        lines.append("*No new Profile B trades from widened filters.*")
        lines.append("")

    # ── 4. Profile A validation ──
    lines.append("## 4. Profile A Validation (MUST BE UNCHANGED)")
    lines.append("")
    lines.append("| Metric | Narrow Baseline | Wide Run |")
    lines.append("|--------|----------------|----------|")
    lines.append(f"| A total sims | {len(narrow_a_all)} | {len(a_sims)} |")
    lines.append(f"| A active trades | {len(narrow_a_active)} | {len(a_active)} |")
    lines.append(f"| A winners | {len(narrow_a_wins)} | {len(a_wins)} |")
    lines.append(f"| A win rate | {narrow_a_wr:.1f}% | {a_wr_wide:.1f}% |")
    lines.append(f"| A total P&L | ${narrow_a_pnl:+,.0f} | ${a_total_pnl:+,.0f} |")
    a_match = abs(a_total_pnl - narrow_a_pnl) < 1.0 and len(a_sims) == len(narrow_a_all)
    lines.append(f"| **Match?** | — | **{'YES' if a_match else 'NO — INVESTIGATE'}** |")
    lines.append("")

    # ── 5. All B trades detail ──
    lines.append("## 5. All Profile B Trades (Wide)")
    lines.append("")
    if b_sims:
        lines.append("| Date | Symbol | SQS | Tier | Risk | P&L | Notes |")
        lines.append("|------|--------|-----|------|------|-----|-------|")
        for d, s, p, pnl, sqs, r, t in b_sims:
            # Check if this is a new trade
            is_new = any(nb['date'] == d and nb['symbol'] == s for nb in stats['new_b_trades'])
            note = "NEW" if is_new else ""
            if pnl != 0:
                note += " ACTIVE" if note else "ACTIVE"
            lines.append(f"| {d} | {s} | {sqs} | {t} | ${r} | ${pnl:+,.0f} | {note} |")
    lines.append("")

    # ── 6. Decision assessment ──
    lines.append("## 6. Decision Assessment")
    lines.append("")
    green = b_wr >= 40 and b_wl_ratio >= 2.0 and worst_b_loss >= -300
    yellow = 30 <= b_wr < 40 and b_total_pnl > 0
    red = b_wr < 30 or (b_wl_ratio < 1.5 and b_wl_ratio != float('inf')) or b_total_pnl < 0

    lines.append("| Criterion | Threshold | Actual | Pass? |")
    lines.append("|-----------|-----------|--------|-------|")
    lines.append(f"| B win rate | >= 40% (GREEN) | {b_wr:.1f}% | {'PASS' if b_wr >= 40 else 'FAIL'} |")
    lines.append(f"| W/L ratio | >= 2:1 (GREEN) | {wl_wide_str} | {'PASS' if b_wl_ratio >= 2.0 else 'FAIL'} |")
    lines.append(f"| No loss > $300 | max loss >= -$300 | ${worst_b_loss:+,.0f} | {'PASS' if worst_b_loss >= -300 else 'FAIL'} |")
    lines.append(f"| Net positive | P&L > $0 | ${b_total_pnl:+,.0f} | {'PASS' if b_total_pnl > 0 else 'FAIL'} |")
    lines.append("")

    if green:
        decision = "GREEN"
        decision_text = "Keep widened filters — all criteria met."
    elif yellow:
        decision = "YELLOW"
        decision_text = "Partial rollback — win rate 30-40% but still positive. Review which filter change is hurting."
    elif red:
        decision = "RED"
        decision_text = "Full rollback — performance degraded below thresholds."
    else:
        decision = "YELLOW"
        decision_text = "Mixed results — review per-filter breakdown before deciding."

    lines.append(f"### Decision: **{decision}**")
    lines.append("")
    lines.append(decision_text)
    lines.append("")

    # ── 7. Overall headline ──
    total = stats['total_sims']
    active = stats['winners'] + stats['losers']
    win_rate = (stats['winners'] / active * 100) if active > 0 else 0
    lines.append("## 7. Overall Headline Metrics (Both Periods)")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| **Total P&L** | **${stats['total_pnl']:+,.0f}** |")
    lines.append(f"| Total Sims | {total} |")
    lines.append(f"| Active Trades | {active} |")
    lines.append(f"| Win Rate (active) | {win_rate:.1f}% |")
    lines.append(f"| Profile A P&L | ${a_total_pnl:+,.0f} |")
    lines.append(f"| Profile B P&L | ${b_total_pnl:+,.0f} |")
    lines.append(f"| Cold Market Skips | {stats['cold_market_days']} |")
    lines.append(f"| Kill Switch Fires | {stats['kill_switch_days']} |")
    lines.append("")

    report = "\n".join(lines)
    report_path = "PROFILE_B_WIDE_FILTER_RESULTS.md"
    with open(report_path, 'w') as f:
        f.write(report)
    print(f"\nReport saved to {report_path}")
    return report


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("  V6.2 WIDE B FILTER BACKTEST — JAN 2025 to FEB 2026")
    print(f"  {len(ALL_DATES)} trading days")
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
        'new_b_trades': [],
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
    b_active = sum(1 for x in b_sims if x[3] != 0)

    print(f"\n{'=' * 60}")
    print(f"  V6.2 WIDE B FILTER — SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Total P&L:         ${stats['total_pnl']:+,.0f}")
    print(f"  Total Sims:        {total}")
    print(f"  Active Trades:     {active}")
    print(f"  Win Rate (active): {win_rate:.1f}%")
    print()
    print(f"  Profile A: {len(a_sims)} sims, ${a_pnl:+,.0f}")
    print(f"  Profile B: {len(b_sims)} sims, {b_active} active, ${b_pnl:+,.0f}")
    print(f"  New B trades: {len(stats['new_b_trades'])}")
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
        'new_b_trades': stats['new_b_trades'],
    }
    stats_path = f"{OUTPUT_DIR}/wide_b_stats.json"
    with open(stats_path, 'w') as f:
        json.dump(report_data, f, indent=2)
    print(f"Stats saved to {stats_path}")

    # Generate comparison report
    generate_report(stats)


if __name__ == "__main__":
    main()
