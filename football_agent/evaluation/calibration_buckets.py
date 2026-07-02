from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable


def bucket_probability(p: float) -> str:
    if p < 0.40:
        return "0-40"
    if p < 0.50:
        return "40-50"
    if p < 0.60:
        return "50-60"
    if p < 0.70:
        return "60-70"
    return "70+"


def summarize(rows: Iterable[Dict]) -> Dict[str, Dict[str, float]]:
    buckets = defaultdict(lambda: {"count": 0, "wins": 0})
    for r in rows:
        b = bucket_probability(float(r.get("model_probability", 0)))
        buckets[b]["count"] += 1
        if r.get("selection") == r.get("actual"):
            buckets[b]["wins"] += 1
    return {k: {"count": v["count"], "hit_rate": (v["wins"] / v["count"] if v["count"] else 0.0)} for k, v in buckets.items()}
