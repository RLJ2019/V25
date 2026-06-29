from __future__ import annotations

from typing import Dict


def format_weekly_evaluation(metrics: Dict) -> str:
    return (
        "📊 <b>V25 Weekevaluatie</b>\n\n"
        f"Aantal picks: {metrics.get('count', 0)}\n"
        f"Brier-score: {metrics.get('brier', 0):.3f}\n"
        f"ROI: {metrics.get('roi', 0):+.1%}\n"
        f"CLV positief: {metrics.get('positive_clv', 0):.1%}\n"
    )
