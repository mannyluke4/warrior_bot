"""
Stock Behavior Classifier — Phase 2

Classifies stocks into behavior types based on observable price action
in the first few minutes of the trading window. Returns a behavior type
and recommended exit strategy parameters.

Usage:
    from classifier import StockClassifier

    classifier = StockClassifier()
    result = classifier.classify(metrics_dict)
    # result.behavior_type = "cascading" | "one_big_move" | "smooth_trend" | ...
    # result.exit_profile = {...}  # recommended exit parameters
    # result.confidence = 0.0-1.0
    # result.reasoning = "VWAP dist 14.2%, 8 new highs in 5m, ..."
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


# ── Exit profiles mapped to each behavior type ──────────────────────

EXIT_PROFILES: dict[str, dict] = {
    "cascading": {
        "description": "Signal mode cascading re-entry — the bot's core edge",
        "suppress_be_under_r": 0.0,
        "suppress_tw_under_r": 0.0,
        "trail_atr_mult": None,
        "max_re_entries": 5,
        "re_entry_cooldown_bars": 3,
    },
    "one_big_move": {
        "description": "Ride the trend — suppress early exits, let trail handle it",
        "suppress_be_under_r": 1.5,
        "suppress_tw_under_r": 2.0,
        "trail_atr_mult": 2.0,
        "max_re_entries": 2,
        "re_entry_cooldown_bars": 10,
    },
    "smooth_trend": {
        "description": "Steady grind up — moderate exit suppression",
        "suppress_be_under_r": 1.0,
        "suppress_tw_under_r": 1.0,
        "trail_atr_mult": 1.5,
        "max_re_entries": 3,
        "re_entry_cooldown_bars": 5,
    },
    "choppy": {
        "description": "High volatility chop — tight stops, quick profits",
        "suppress_be_under_r": 0.0,
        "suppress_tw_under_r": 0.0,
        "trail_atr_mult": 0.8,
        "max_re_entries": 1,
        "re_entry_cooldown_bars": 15,
    },
    "early_bird": {
        "description": "Decent setup, standard approach with moderate patience",
        "suppress_be_under_r": 0.5,
        "suppress_tw_under_r": 0.5,
        "trail_atr_mult": 1.2,
        "max_re_entries": 3,
        "re_entry_cooldown_bars": 5,
    },
    "uncertain": {
        "description": "Unknown pattern — trade conservatively",
        "suppress_be_under_r": 0.0,
        "suppress_tw_under_r": 0.0,
        "trail_atr_mult": 1.0,
        "max_re_entries": 2,
        "re_entry_cooldown_bars": 5,
    },
    "avoid": {
        "description": "No edge detected — skip this stock",
        "suppress_be_under_r": None,
        "suppress_tw_under_r": None,
        "trail_atr_mult": None,
        "max_re_entries": 0,
        "re_entry_cooldown_bars": None,
    },
}


@dataclass
class ClassifierResult:
    behavior_type: str                    # "cascading", "one_big_move", etc.
    exit_profile: dict                    # From EXIT_PROFILES
    confidence: float                     # 0.0 to 1.0
    reasoning: str                        # Human-readable explanation
    metrics_snapshot: dict                # The raw metrics used
    classification_time_minutes: int      # Minutes of data used
    previous_classifications: list = field(default_factory=list)


class StockClassifier:
    """Rule-based stock behavior classifier with configurable thresholds."""

    def __init__(self):
        # Gate thresholds (env-configurable)
        self.vwap_gate = float(os.getenv("WB_CLASSIFIER_VWAP_GATE", "5"))
        self.range_gate = float(os.getenv("WB_CLASSIFIER_RANGE_GATE", "10"))
        self.nh_gate = int(os.getenv("WB_CLASSIFIER_NH_GATE", "2"))
        self.reclass_enabled = os.getenv("WB_CLASSIFIER_RECLASS_ENABLED", "1") == "1"

    # ── Main classify method ────────────────────────────────────────

    def classify(self, metrics: dict, minutes: int = 5) -> ClassifierResult:
        """Classify a stock based on behavioral metrics snapshot.

        Args:
            metrics: dict of behavioral metrics (from BehaviorMetrics.snapshot_at()
                     or loaded from study JSON).
            minutes: how many minutes of data the metrics represent.

        Returns:
            ClassifierResult with behavior type and exit profile.
        """
        nh = metrics.get("new_high_count", 0)
        pb = metrics.get("pullback_count", 0)
        pb_depth = metrics.get("pullback_depth_avg_pct", 0)
        green_ratio = metrics.get("green_bar_ratio", 0)
        vwap_dist = metrics.get("max_vwap_distance_pct", 0)
        price_range = metrics.get("price_range_pct", 0)
        vol_total = metrics.get("vol_total", 0)
        reasons: list[str] = []

        # ── Stage 1: Pre-entry gate ─────────────────────────────────
        if (vwap_dist < self.vwap_gate
                and price_range < self.range_gate
                and nh < self.nh_gate):
            reasons.append(
                f"AVOID gate: VWAP dist {vwap_dist:.1f}% < {self.vwap_gate}%, "
                f"range {price_range:.1f}% < {self.range_gate}%, "
                f"NH {nh} < {self.nh_gate}"
            )
            return ClassifierResult(
                behavior_type="avoid",
                exit_profile=EXIT_PROFILES["avoid"],
                confidence=0.85,
                reasoning="; ".join(reasons),
                metrics_snapshot=metrics,
                classification_time_minutes=minutes,
            )

        # ── Stage 2: Behavior classification ────────────────────────

        # CASCADING: lots of new highs + pullbacks + meaningful depth
        if nh >= 6 and pb >= 3 and pb_depth >= 2:
            btype = "cascading"
            conf = min(1.0, 0.6 + (nh - 6) * 0.05 + (pb - 3) * 0.05)
            reasons.append(
                f"Cascading: {nh} new highs, {pb} pullbacks, "
                f"{pb_depth:.1f}% avg depth"
            )

        # ONE BIG MOVE: extreme VWAP dist + huge range
        elif vwap_dist >= 20 and price_range >= 50:
            btype = "one_big_move"
            conf = min(1.0, 0.6 + (vwap_dist - 20) * 0.01)
            reasons.append(
                f"One big move: VWAP dist {vwap_dist:.1f}%, "
                f"range {price_range:.1f}%"
            )

        # SMOOTH TREND: new highs, few pullbacks, mostly green
        elif nh >= 3 and pb <= 1 and green_ratio >= 0.6:
            btype = "smooth_trend"
            conf = min(1.0, 0.5 + nh * 0.05 + green_ratio * 0.2)
            reasons.append(
                f"Smooth trend: {nh} new highs, {pb} pullbacks, "
                f"green ratio {green_ratio:.2f}"
            )

        # CHOPPY: deep pullbacks, mixed direction
        elif pb_depth >= 10 and green_ratio < 0.50:
            btype = "choppy"
            conf = min(1.0, 0.5 + pb_depth * 0.02)
            reasons.append(
                f"Choppy: {pb_depth:.1f}% avg pullback depth, "
                f"green ratio {green_ratio:.2f}"
            )

        # EARLY BIRD: moderate VWAP dist + decent volume
        elif vwap_dist >= 8 and vol_total >= 500_000:
            btype = "early_bird"
            conf = 0.5
            reasons.append(
                f"Early bird: VWAP dist {vwap_dist:.1f}%, "
                f"vol {vol_total:,.0f}"
            )

        # UNCERTAIN: fallback
        else:
            btype = "uncertain"
            conf = 0.3
            reasons.append(
                f"No strong pattern: NH={nh}, PB={pb}, "
                f"green={green_ratio:.2f}, VWAP={vwap_dist:.1f}%, "
                f"range={price_range:.1f}%"
            )

        return ClassifierResult(
            behavior_type=btype,
            exit_profile=EXIT_PROFILES[btype],
            confidence=round(conf, 2),
            reasoning="; ".join(reasons),
            metrics_snapshot=metrics,
            classification_time_minutes=minutes,
        )

    # ── Reclassification at 10m / 15m ──────────────────────────────

    def reclassify(self, metrics: dict, current: ClassifierResult,
                   minutes: int) -> ClassifierResult:
        """Re-evaluate classification with more data.

        Returns a new result (may or may not change the type).
        Preserves classification history.
        """
        new = self.classify(metrics, minutes=minutes)

        # Upgrade rules
        if current.behavior_type == "uncertain":
            nh = metrics.get("new_high_count", 0)
            if nh >= 4:
                pb = metrics.get("pullback_count", 0)
                if pb >= 2:
                    new = self.classify(metrics, minutes=minutes)
                    # Force cascading if the fresh classify didn't catch it
                    if new.behavior_type == "uncertain":
                        new = ClassifierResult(
                            behavior_type="cascading",
                            exit_profile=EXIT_PROFILES["cascading"],
                            confidence=0.55,
                            reasoning=f"Upgraded from uncertain at {minutes}m: "
                                      f"NH={nh}, PB={pb}",
                            metrics_snapshot=metrics,
                            classification_time_minutes=minutes,
                        )
                else:
                    if new.behavior_type == "uncertain":
                        new = ClassifierResult(
                            behavior_type="smooth_trend",
                            exit_profile=EXIT_PROFILES["smooth_trend"],
                            confidence=0.50,
                            reasoning=f"Upgraded from uncertain at {minutes}m: "
                                      f"NH={nh}, PB={pb}",
                            metrics_snapshot=metrics,
                            classification_time_minutes=minutes,
                        )

        # Downgrade: if VWAP dist collapsed, downgrade to avoid
        vwap_dist = metrics.get("max_vwap_distance_pct", 0)
        if current.behavior_type != "avoid" and vwap_dist < 3:
            new = ClassifierResult(
                behavior_type="avoid",
                exit_profile=EXIT_PROFILES["avoid"],
                confidence=0.7,
                reasoning=f"Downgraded at {minutes}m: "
                          f"VWAP dist collapsed to {vwap_dist:.1f}%",
                metrics_snapshot=metrics,
                classification_time_minutes=minutes,
            )

        # Cascading → smooth_trend if pullbacks stopped
        if current.behavior_type == "cascading":
            pb = metrics.get("pullback_count", 0)
            nh = metrics.get("new_high_count", 0)
            if pb <= 1 and nh >= 4:
                new = ClassifierResult(
                    behavior_type="smooth_trend",
                    exit_profile=EXIT_PROFILES["smooth_trend"],
                    confidence=0.55,
                    reasoning=f"Reclassified from cascading at {minutes}m: "
                              f"pullbacks stopped (PB={pb}, NH={nh})",
                    metrics_snapshot=metrics,
                    classification_time_minutes=minutes,
                )

        # Track history
        new.previous_classifications = (
            current.previous_classifications
            + [{"type": current.behavior_type,
                "confidence": current.confidence,
                "minutes": current.classification_time_minutes}]
        )
        return new

    # ── Retroactive classification from study JSON ──────────────────

    @staticmethod
    def classify_from_json(json_path: str) -> ClassifierResult:
        """Load a study_data JSON file and classify from 30m stock_metrics.

        This is used for validation — classifies based on the full 30-minute
        metrics (since snapshot_at isn't available for existing JSONs).
        """
        with open(json_path) as f:
            data = json.load(f)

        sm = data.get("stock_metrics", {})
        if not sm:
            return ClassifierResult(
                behavior_type="avoid",
                exit_profile=EXIT_PROFILES["avoid"],
                confidence=0.0,
                reasoning="No stock_metrics in JSON",
                metrics_snapshot={},
                classification_time_minutes=0,
            )

        # Map 30m metric names → classifier metric names
        metrics = {
            "new_high_count": sm.get("new_high_count_30m", 0),
            "pullback_count": sm.get("pullback_count_30m", 0),
            "pullback_depth_avg_pct": sm.get("pullback_depth_avg_pct", 0),
            "green_bar_ratio": sm.get("green_bar_ratio_30m", 0),
            "max_vwap_distance_pct": sm.get("max_vwap_distance_pct", 0),
            "price_range_pct": sm.get("price_range_30m_pct", 0),
            "vol_total": sm.get("vol_total_30m", 0),
        }

        classifier = StockClassifier()
        return classifier.classify(metrics, minutes=30)
