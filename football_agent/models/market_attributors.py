from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from football_agent.schemas import MatchAnalysis, ValueDecision


@dataclass
class MarketAttribution:
    market: str
    selection: str
    summary: str
    positive_factors: List[str]
    negative_factors: List[str]
    raw: Dict

    def as_dict(self) -> Dict:
        return {
            "market": self.market,
            "selection": self.selection,
            "summary": self.summary,
            "positive_factors": self.positive_factors,
            "negative_factors": self.negative_factors,
            "raw": self.raw,
        }


class MarketAttributor:
    def attribute(self, analysis: MatchAnalysis, value: ValueDecision) -> MarketAttribution:
        raise NotImplementedError


class OneXTwoAttributor(MarketAttributor):
    def attribute(self, analysis: MatchAnalysis, value: ValueDecision) -> MarketAttribution:
        attr_map = {
            "HOME": analysis.attribution_home,
            "DRAW": analysis.attribution_draw,
            "AWAY": analysis.attribution_away,
        }
        attr = attr_map.get(value.selection)
        positives: List[str] = []
        negatives: List[str] = []
        if attr:
            if attr.xg_form_adjustment > 0:
                positives.append("Onderliggende vorm/xG ondersteunt deze kant.")
            elif attr.xg_form_adjustment < 0:
                negatives.append("Onderliggende vorm/xG werkt tegen deze kant.")
            if attr.injury_impact > 0:
                positives.append("Blessure- of teamnieuws valt gunstig uit.")
            elif attr.injury_impact < 0:
                negatives.append("Blessure- of teamnieuws verhoogt het risico.")
            if attr.fatigue_impact > 0:
                positives.append("Rust/schema werkt in het voordeel.")
            elif attr.fatigue_impact < 0:
                negatives.append("Rust/schema is een aandachtspunt.")
        return MarketAttribution(
            market=value.market,
            selection=value.selection,
            summary="1X2-selectie beoordeeld op teamsterkte, vorm, schema, blessures en marktprijs.",
            positive_factors=positives,
            negative_factors=negatives,
            raw=attr.as_dict() if attr else {},
        )


class OverUnderAttributor(MarketAttributor):
    def attribute(self, analysis: MatchAnalysis, value: ValueDecision) -> MarketAttribution:
        positives: List[str] = []
        negatives: List[str] = []
        total_xg = None
        if analysis.poisson:
            total_xg = analysis.poisson.home_xg + analysis.poisson.away_xg
            if value.selection == "OVER_2_5":
                if total_xg >= 2.75:
                    positives.append("De verwachte totale doelpunten liggen duidelijk boven de grens.")
                elif total_xg < 2.45:
                    negatives.append("De verwachte totale doelpunten liggen dicht bij of onder de grens.")
            elif value.selection == "UNDER_2_5":
                if total_xg <= 2.25:
                    positives.append("De verwachte totale doelpunten liggen duidelijk onder de grens.")
                elif total_xg > 2.65:
                    negatives.append("De verwachte totale doelpunten liggen aan de hoge kant voor under.")
        if analysis.uncertainty_score <= 4:
            positives.append("De onzekerheidsmarge is relatief laag.")
        return MarketAttribution(
            market=value.market,
            selection=value.selection,
            summary="Goals-markt beoordeeld op verwachte doelpunten, teamvorm, tempo-risico en marktprijs.",
            positive_factors=positives,
            negative_factors=negatives,
            raw={"total_xg": total_xg, "over_under": analysis.poisson.over_under if analysis.poisson else {}},
        )


class BTTSAttributor(MarketAttributor):
    def attribute(self, analysis: MatchAnalysis, value: ValueDecision) -> MarketAttribution:
        positives: List[str] = []
        negatives: List[str] = []
        home_xg = away_xg = None
        if analysis.poisson:
            home_xg = analysis.poisson.home_xg
            away_xg = analysis.poisson.away_xg
            if value.selection == "BTTS_YES":
                if home_xg >= 1.1 and away_xg >= 1.0:
                    positives.append("Beide teams hebben voldoende scoringsverwachting.")
                if min(home_xg, away_xg) < 0.85:
                    negatives.append("Eén team heeft een lage scoringsverwachting.")
            elif value.selection == "BTTS_NO":
                if min(home_xg, away_xg) < 0.85:
                    positives.append("Eén team heeft een lage scoringsverwachting.")
                if home_xg >= 1.2 and away_xg >= 1.1:
                    negatives.append("Beide teams hebben voldoende scoringsverwachting, dus BTTS No is riskanter.")
        return MarketAttribution(
            market=value.market,
            selection=value.selection,
            summary="BTTS-markt beoordeeld op scoringskansen van beide teams en marktprijs.",
            positive_factors=positives,
            negative_factors=negatives,
            raw={"home_xg": home_xg, "away_xg": away_xg, "btts": analysis.poisson.btts if analysis.poisson else {}},
        )


class MarketAttributionFactory:
    def __init__(self):
        self.one_x_two = OneXTwoAttributor()
        self.over_under = OverUnderAttributor()
        self.btts = BTTSAttributor()

    def attribute(self, analysis: MatchAnalysis, value: ValueDecision) -> Dict:
        if value.market == "OVER_UNDER_2_5":
            return self.over_under.attribute(analysis, value).as_dict()
        if value.market == "BTTS":
            return self.btts.attribute(analysis, value).as_dict()
        return self.one_x_two.attribute(analysis, value).as_dict()
