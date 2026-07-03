from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from football_agent.settlement.base import FixtureResult, SettlementInput
from football_agent.settlement.btts import settle_btts
from football_agent.settlement.clv import OddsQuote, calculate_clv
from football_agent.settlement.market_mapping import MarketMappingError, normalize_pick_market_selection_line
from football_agent.settlement.one_x_two import settle_1x2
from football_agent.settlement.policies import status_precheck
from football_agent.settlement.totals import settle_totals


class V2513SettlementPipelineTests(unittest.TestCase):
    def test_totals_split_line_rejection(self):
        with self.assertRaises(MarketMappingError) as ctx:
            normalize_pick_market_selection_line("OVER_UNDER", "OVER_2_25", Decimal("2.25"))
        self.assertEqual(ctx.exception.code, "SKIPPED_UNSUPPORTED_LINE")

    def test_clv_overround_floating_precision(self):
        result = calculate_clv(
            entry_odds=Decimal("21.00"),
            model_probability=Decimal("0.055"),
            market="1X2",
            selection="AWAY",
            closing_bookmaker="sharpbook",
            quotes=[
                OddsQuote("sharpbook", "1X2", "HOME", Decimal("1.05"), "s1"),
                OddsQuote("sharpbook", "1X2", "DRAW", Decimal("11.00"), "s1"),
                OddsQuote("sharpbook", "1X2", "AWAY", Decimal("21.00"), "s1"),
            ],
        )
        self.assertEqual(result.clv_method, "NO_VIG_SAME_BOOKMAKER")
        self.assertIsNotNone(result.overround)
        self.assertGreater(result.overround, Decimal("1"))
        self.assertIsNotNone(result.clv_model_vs_close)

    def test_postponed_grace_period_transition(self):
        os.environ["POSTPONED_VOID_AFTER_HOURS"] = "36"
        now = datetime(2026, 7, 3, 12, 0, tzinfo=timezone.utc)
        kickoff_30h = (now - timedelta(hours=30)).isoformat().replace("+00:00", "Z")
        kickoff_37h = (now - timedelta(hours=37)).isoformat().replace("+00:00", "Z")

        within = status_precheck(FixtureResult("af-1", "PST", kickoff_utc=kickoff_30h), now)
        expired = status_precheck(FixtureResult("af-1", "PST", kickoff_utc=kickoff_37h), now)

        self.assertIsNotNone(within)
        self.assertEqual(within.status, "SKIPPED")
        self.assertEqual(within.settlement_basis, "POSTPONED_WITHIN_GRACE_PERIOD")
        self.assertIsNotNone(expired)
        self.assertEqual(expired.status, "VOID")
        self.assertEqual(expired.settlement_basis, "POSTPONED_GRACE_EXPIRED")

    def test_abandoned_mathematical_certainty(self):
        result = FixtureResult("af-2", "ABD", home_score=2, away_score=1)
        btts_pick = SettlementInput("p1", "af-2", "BTTS", "BTTS_YES", Decimal("1"), Decimal("1.80"))
        over_pick = SettlementInput("p2", "af-2", "OVER_UNDER", "OVER", Decimal("1"), Decimal("1.90"), line=Decimal("2.5"))
        x2_pick = SettlementInput("p3", "af-2", "1X2", "HOME", Decimal("1"), Decimal("2.10"))

        btts = settle_btts(btts_pick, result)
        over = settle_totals(over_pick, result)
        one_x_two = settle_1x2(x2_pick, result)

        self.assertEqual(btts.status, "WIN")
        self.assertEqual(over.status, "WIN")
        self.assertEqual(one_x_two.status, "VOID")

    def test_clv_benchmark_fallback_when_same_bookmaker_incomplete(self):
        os.environ["CLV_BENCHMARK_BOOKMAKER_PRIORITY"] = "pinnacle"
        result = calculate_clv(
            entry_odds=Decimal("2.20"),
            model_probability=Decimal("0.48"),
            market="1X2",
            selection="HOME",
            closing_bookmaker="softbook",
            quotes=[
                OddsQuote("softbook", "1X2", "HOME", Decimal("2.20"), "soft-home"),
                OddsQuote("pinnacle", "1X2", "HOME", Decimal("2.10"), "pin-home"),
                OddsQuote("pinnacle", "1X2", "DRAW", Decimal("3.30"), "pin-draw"),
                OddsQuote("pinnacle", "1X2", "AWAY", Decimal("3.60"), "pin-away"),
            ],
        )
        self.assertEqual(result.clv_method, "NO_VIG_BENCHMARK_BOOKMAKER")
        self.assertEqual(result.closing_bookmaker, "pinnacle")
        self.assertEqual(result.clv_warning, "SAME_BOOKMAKER_INCOMPLETE")

    def test_clv_consensus_fallback_when_benchmark_missing(self):
        os.environ["CLV_BENCHMARK_BOOKMAKER_PRIORITY"] = "pinnacle"
        os.environ["CLV_MIN_COMPLETE_BOOKMAKERS_FOR_CONSENSUS"] = "2"
        result = calculate_clv(
            entry_odds=Decimal("1.90"),
            model_probability=Decimal("0.56"),
            market="BTTS",
            selection="BTTS_YES",
            closing_bookmaker="softbook",
            quotes=[
                OddsQuote("book_a", "BTTS", "BTTS_YES", Decimal("1.91"), "a-y"),
                OddsQuote("book_a", "BTTS", "BTTS_NO", Decimal("1.91"), "a-n"),
                OddsQuote("book_b", "BTTS", "BTTS_YES", Decimal("1.88"), "b-y"),
                OddsQuote("book_b", "BTTS", "BTTS_NO", Decimal("1.95"), "b-n"),
            ],
        )
        self.assertEqual(result.clv_method, "NO_VIG_CONSENSUS_MARKET")
        self.assertEqual(result.closing_bookmaker, "consensus")


if __name__ == "__main__":
    unittest.main()
