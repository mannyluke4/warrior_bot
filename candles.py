# candles.py
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class CandleParts:
    body: float
    upper_wick: float
    lower_wick: float
    rng: float
    green: bool

def candle_parts(o: float, h: float, l: float, c: float) -> CandleParts:
    rng = max(1e-9, h - l)
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    return CandleParts(
        body=body,
        upper_wick=max(0.0, upper),
        lower_wick=max(0.0, lower),
        rng=rng,
        green=(c >= o),
    )

def is_doji(o: float, h: float, l: float, c: float, body_frac: float = 0.12) -> bool:
    p = candle_parts(o, h, l, c)
    return (p.body / p.rng) <= body_frac

def is_hammer(o: float, h: float, l: float, c: float,
              min_lower_to_body: float = 2.0,
              max_upper_to_body: float = 0.7) -> bool:
    p = candle_parts(o, h, l, c)
    body = max(p.body, 1e-9)
    return (p.lower_wick / body) >= min_lower_to_body and (p.upper_wick / body) <= max_upper_to_body

def is_shooting_star(o: float, h: float, l: float, c: float,
                     min_upper_to_body: float = 2.0,
                     max_lower_to_body: float = 0.7) -> bool:
    p = candle_parts(o, h, l, c)
    body = max(p.body, 1e-9)
    return (p.upper_wick / body) >= min_upper_to_body and (p.lower_wick / body) <= max_lower_to_body

def is_bullish_engulfing(o1: float, h1: float, l1: float, c1: float,
                         o0: float, h0: float, l0: float, c0: float) -> bool:
    """
    Current candle (1) bullish engulfing previous candle (0).
    Rules:
      - Prev candle red (c0 < o0)
      - Current candle green (c1 > o1)
      - Current real body engulfs previous real body:
            o1 <= c0  and  c1 >= o0
    """
    if not (c0 < o0 and c1 > o1):
        return False
    return (o1 <= c0) and (c1 >= o0)


def is_bearish_engulfing(o1: float, h1: float, l1: float, c1: float,
                         o0: float, h0: float, l0: float, c0: float) -> bool:
    """
    Current candle (1) bearish engulfing previous candle (0).
    Rules:
      - Prev candle green (c0 > o0)
      - Current candle red (c1 < o1)
      - Current real body engulfs previous real body:
            o1 >= c0  and  c1 <= o0
    """
    if not (c0 > o0 and c1 < o1):
        return False
    return (o1 >= c0) and (c1 <= o0)