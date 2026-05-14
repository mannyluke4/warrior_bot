# WB Winners vs. Squeeze Watchlist: Filter-Origin Analysis

**Window:** 2026-05-04 → 2026-05-13 (8 trading days, alpaca sub-bot)
**Source logs:** `~/warrior_bot_v2/logs/2026-05-DD_subbot_alpaca.log`, `scanner_results/live_2026-05-DD_*.json`, `~/warrior_bot_v2/logs/2026-05-DD_scanner.log`
**Live filter thresholds in `.env`:** `WB_MIN_GAP_PCT=5`, `WB_MIN_PRICE=2.00`, `WB_MAX_PRICE=20.00`, `WB_MAX_FLOAT=20M`, `WB_MIN_REL_VOLUME=1.5`, `WB_MIN_PM_VOLUME=30,000`
(Prompt cited 10/15/2.0/50K; actual live values are looser — `.env` already moved.)

## A. All WB Trades (n=19)

| # | Date | Sym | Enter ET | Exit ET | Qty | Fill $ | Exit $ | Realized P&L | Score | Result |
|---|------|-----|----------|---------|-----|--------|--------|--------------|-------|--------|
| 1 | 05-05 | CLNN | 10:42 | 10:46 | 7,256 | 6.91 | 6.82 | -$653 | 7 | LOSS |
| 2 | 05-05 | CLNN | 11:08 | 11:09 | 7,352 | 6.82 | 6.75 | -$515 | 7 | LOSS |
| 3 | 05-05 | FATN | 11:56 | 12:00 | 15,923 | 3.16 | 3.10 | -$955 | 8 | LOSS |
| 4 | 05-05 | CLNN | 14:37 | 14:38 | 7,480 | 6.69 | 6.60 | -$673 | 9 | LOSS |
| 5 | **05-05** | **FATN** | **14:39** | **14:41** | **15,337** | **3.28** | **3.35** | **+$1,074** | **8** | **WIN** |
| 6 | 05-05 | CLNN | 14:56 | 15:01 | 7,513 | 6.70 | 6.56 | -$1,052 | 7 | LOSS |
| 7 | 05-08 | SST | 15:01 | 15:03 | 12,531 | 3.99 | 3.97 | -$251 | 9 | LOSS |
| 8 | 05-08 | FATN | 13:58 | 15:43 | 15,432 | 3.26 | 3.21 | -$772 | 10 | LOSS |
| 9 | **05-08** | **ATRA** | **17:09** | **19:37** | **5,813** | **8.65** | **9.08** | **+$2,500** | **10** | **WIN** |
| 10 | 05-11 | NVOX | 10:12 | 10:13 | 1,948 | 16.22 | 16.20 | -$37 | 9 | LOSS |
| 11 | 05-11 | ATRA | 13:52 | 14:05 | 3,666 | 8.47 | 8.33 | -$513 | 10 | LOSS |
| 12 | **05-11** | **SST** | **14:18** | **15:01** | **8,040** | **3.83** | **4.09** | **+$2,090** | **9** | **WIN** |
| 13 | 05-11 | ATRA | 18:30 | 19:02 | 2,684 | 9.49 | 9.20 | -$778 | 10 | LOSS |
| 14 | 05-12 | ENSC | 08:16 | 08:19 | 79,449 | 0.3291 | 0.3210 | -$644 | 9 | LOSS |
| 15 | 05-12 | SST | 11:20 | 11:21 | 7,905 | 3.94 | 3.83 | -$870 | 10 | LOSS |
| 16 | 05-12 | ENSC | 14:54 | 14:57 | 75,667 | 0.3354 | 0.3285 | -$519 | 9 | LOSS |
| 17 | 05-12 | TRAW | 15:17 | 15:18 | 16,526 | 1.82 | 1.78 | -$661 | 9 | LOSS |
| 18 | 05-13 | ENSC | 11:53 | 11:59 | 72,665 | 0.3011 | 0.2941 | -$509 | 10 | LOSS |
| 19 | **05-13** | **MEI** | **16:06** | **16:19** | **2,032** | **14.05** | **14.23** | **+$366** | **7** | **WIN** |

**Summary:** 4 wins / 15 losses (21% win rate). Net P&L across the 19 trades: **-$2,381**. Without the four winners (+$6,030), the loss side alone is -$8,411. Sample is small (n=19) and noisy — treat findings as directional.

## B. Scanner Stats for the 4 Winners (Closest Snapshot Available)

| Win | Source | gap_pct | price | float_m | pm_volume | rvol | rank_score | passes_relaxed_WB_filter |
|-----|--------|---------|-------|---------|-----------|------|------------|--------------------------|
| FATN 05-05 | no JSON snap (5-04/5-05 dir empty); subbot log @ 14:30 ET shows VWAP=$3.17, price=$3.24, HOD=$3.31, avg_vol≈1,200 sh/bar | ~+5% (price 3.24 vs prev close ~3.10) | 3.24 | unknown | extremely thin (~1K sh/min midday) | n/a | n/a | YES (loose) |
| ATRA 05-08 | `live_2026-05-08_update_0929.json` (last PM snap before entry @ 17:09) | **+68.5%** | 8.68 | **4.25** | **4,103** | 0.06 | 0.336 | YES |
| SST 05-11 | not in 5-11 watchlist JSON (carryover); last 5-07 scanner row | **+17.6%** | 4.68 | **4.54** | **171** | 0.0 | 0.174 | YES |
| MEI 05-13 | no JSON snap; daily.log CHART @ 15:40 ET shows VWAP=$13.31, price≈$13.91 | **~+4–5%** (gap below squeeze floor) | 13.91 | unknown | ultra-thin (V=100-400 sh/bar) | n/a | n/a | borderline (gap<5%) |

`would_pass_relaxed_WB_filter` = (gap≥5%) AND (price 1-30) AND (pm_volume>0). All four pass loosely; **none of the four winners would pass the squeeze live `WB_MIN_PM_VOLUME=30,000` floor at their last-known PM snapshot.**

## C. Summary Stats — WB Winners Only

- **n_winners = 4** (very small sample)
- **pm_volume distribution at last-known PM snapshot:** min 171, 25th≈170, median ≈ ~2,100, 75th ≈ ~4,100, max ≈ 4,103. (FATN/MEI lack JSON; both are clearly <5K from chart data.)
- **gap_pct distribution:** min ~4%, 25th ~5%, median ~11%, 75th ~37%, max 68.5%.
- **Winners with pm_volume < 30,000 (would be filtered today):** 4 of 4 (100%).
- **Winners with gap < 10% (current `.env` MIN is 5%):** 2 of 4 (FATN 05-05 ~5%, MEI 05-13 ~4–5%).
- **Barely-squeaked-past-squeeze cases:** All four. The squeeze 30K PM-volume floor is *not* what put them on the watchlist on the day they won — they appeared via either (a) prior-day persistence in `watchlist.txt` (FATN, SST, ATRA were carryover symbols seen on 5-04/5-07 squeeze scans) or (b) huge gap dwarfing low PM volume (ATRA 5-08 at +68% gap, but only 4K PM volume).

## D. Recommendation

The data **partially supports** a separate WB scanner, but the sample is too small for a confident "yes/build it" call. Three observations:

1. **The squeeze PM-volume gate is irrelevant to WB winners.** Every winner had pm_volume well below 30K at the last-known PM mark. They reached the watchlist via gap_pct (ATRA, SST) or via overnight persistence (FATN was carried from 5-04, MEI bypassed the scanner entirely on 5-13). A separate WB scanner that drops the PM-volume floor (e.g. to 0–5K) would capture similar setups *without* losing the squeeze edge.

2. **WB winners care about intraday wave structure, not premarket squeeze.** The MEI 5-13 win (only ~+4% gap, intraday wave at 16:06 ET) is the cleanest case — there is no plausible premarket squeeze filter that would have flagged it; an intraday gap-from-VWAP / RVOL-by-minute scanner would. Same shape applies to FATN 5-05 (entry at 14:39 ET on a midday breakout).

3. **Caveat — winners are noisy.** 4/19 = 21% win rate with one outlier (+$2,500 ATRA) carries the P&L. Building a dedicated WB scanner only pays off if it also reduces the 15 losers, not just adds more candidates. The losers also passed the squeeze filter and lost — so loosening the gate could net *worse* P&L unless the WB scanner adds intraday gates (sustained RVOL, time-of-day, wave-context).

**Recommendation:** Don't build a parallel premarket WB scanner yet. Instead, add an **intraday WB candidate adder** — a lightweight loop that pulls symbols meeting (gap≥3% AND intraday RVOL≥3× AND price 2-30) at 15-minute intervals during RTH, appending to the WB-only universe. This captures the MEI 5-13 / FATN 5-05 pattern without touching the squeeze pipeline. Revisit after 4-6 more weeks (≥60 WB trades) to decide if a dedicated PM-scanner pays off.

**Data quality notes:** (a) Scanner JSON snapshots only exist for 5-07, 5-08, 5-11 and only 07:15-09:29 ET (PM only). 5-04/5-05/5-06/5-12/5-13 have no JSON. (b) FATN 5-05, SST 5-11, MEI 5-13 stats reconstructed from daily.log CHART lines and prior-day scanner rows. (c) Carryover via `watchlist.txt` is the actual mechanism — not a fresh scan — that put FATN/SST on the day-of watchlist.
