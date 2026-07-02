from __future__ import annotations

from football_agent.schemas import MatchAnalysis


class RiskFilter:
    def reject_extreme_uncertainty(self, analysis: MatchAnalysis) -> bool:
        return analysis.risk_score >= 7.0 or analysis.data_quality < 5.0
