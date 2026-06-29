from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable


def summarize_by_competition(rows: Iterable[Dict]) -> Dict[str, Dict[str, float]]:
    agg = defaultdict(lambda: {"count": 0, "correct": 0, "profit": 0.0, "stake": 0.0})
    for r in rows:
        key = r.get("competition_key", "unknown")
        agg[key]["count"] += 1
        agg[key]["stake"] += float(r.get("stake", 1.0))
        agg[key]["profit"] += float(r.get("profit", 0.0))
        if r.get("selection") == r.get("actual"):
            agg[key]["correct"] += 1
    return {
        k: {
            "count": v["count"],
            "accuracy": v["correct"] / v["count"] if v["count"] else 0.0,
            "roi": v["profit"] / v["stake"] if v["stake"] else 0.0,
        }
        for k, v in agg.items()
    }
