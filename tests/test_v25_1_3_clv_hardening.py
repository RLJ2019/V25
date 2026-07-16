from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace

from football_agent.settlement.base import (
    FixtureResult,
    SettlementInput,
    SettlementOutcome,
)
from football_agent.settlement.clv import OddsQuote, calculate_clv
from football_agent.settlement.service import SettlementService


class V2513ClvHardeningTests(unittest.TestCase):
    def test_clv_uses_latest_complete_pre_kickoff_bundle(self):
        result = calculate_clv(
            entry_odds=Decimal("2.30"),
            model_probability=Decimal("0.50"),
            market="1X2",
            selection="HOME",
            closing_bookmaker="sharpbook",
            kickoff_utc="2026-07-01T12:00:00Z",
            quotes=[
                # Complete bundle at 11:58. Seconds may differ, but this is one UTC minute.
                OddsQuote(
                    "sharpbook", "1X2", "HOME", Decimal("2.20"),
                    "pre-home", "2026-07-01T11:58:05Z",
                ),
                OddsQuote(
                    "sharpbook", "1X2", "DRAW", Decimal("3.30"),
                    "pre-draw", "2026-07-01T11:58:20Z",
                ),
                OddsQuote(
                    "sharpbook", "1X2", "AWAY", Decimal("3.60"),
                    "pre-away", "2026-07-01T11:58:45Z",
                ),

                # Newer minute, but incomplete: must not replace the complete bundle.
                OddsQuote(
                    "sharpbook", "1X2", "HOME", Decimal("2.10"),
                    "incomplete-home", "2026-07-01T11:59:10Z",
                ),

                # Complete but after kickoff: must always be ignored.
                OddsQuote(
                    "sharpbook", "1X2", "HOME", Decimal("1.90"),
                    "post-home", "2026-07-01T12:01:05Z",
                ),
                OddsQuote(
                    "sharpbook", "1X2", "DRAW", Decimal("3.60"),
                    "post-draw", "2026-07-01T12:01:20Z",
                ),
                OddsQuote(
                    "sharpbook", "1X2", "AWAY", Decimal("4.20"),
                    "post-away", "2026-07-01T12:01:40Z",
                ),
            ],
        )

        self.assertEqual(result.clv_method, "NO_VIG_SAME_BOOKMAKER")
        self.assertEqual(result.closing_odds, Decimal("2.20"))
        self.assertEqual(result.closing_snapshot_id, "pre-home")

    def test_clv_does_not_mix_outcomes_from_different_minutes(self):
        result = calculate_clv(
            entry_odds=Decimal("2.10"),
            model_probability=Decimal("0.52"),
            market="1X2",
            selection="HOME",
            closing_bookmaker="softbook",
            kickoff_utc="2026-07-01T12:00:00Z",
            quotes=[
                # HOME is from 11:58.
                OddsQuote(
                    "softbook", "1X2", "HOME", Decimal("2.00"),
                    "home-1158", "2026-07-01T11:58:30Z",
                ),

                # DRAW and AWAY are from a different minute.
                OddsQuote(
                    "softbook", "1X2", "DRAW", Decimal("3.30"),
                    "draw-1159", "2026-07-01T11:59:10Z",
                ),
                OddsQuote(
                    "softbook", "1X2", "AWAY", Decimal("3.80"),
                    "away-1159", "2026-07-01T11:59:20Z",
                ),
            ],
        )

        # There is no complete same-minute bundle, so no-vig is not allowed.
        self.assertEqual(result.clv_method, "IMPLIED_FALLBACK")
        self.assertEqual(result.clv_warning, "MISSING_COMPLEMENTARY_ODDS")

    def test_clv_exposes_no_vig_closing_probability(self):
        result = calculate_clv(
            entry_odds=Decimal("2.10"),
            model_probability=Decimal("0.55"),
            market="1X2",
            selection="HOME",
            closing_bookmaker="sharpbook",
            quotes=[
                OddsQuote("sharpbook", "1X2", "HOME", Decimal("2.00"), "h"),
                OddsQuote("sharpbook", "1X2", "DRAW", Decimal("3.20"), "d"),
                OddsQuote("sharpbook", "1X2", "AWAY", Decimal("4.00"), "a"),
            ],
        )

        expected_probability = (
            Decimal("1") / Decimal("2.00")
        ) / (
            Decimal("1") / Decimal("2.00")
            + Decimal("1") / Decimal("3.20")
            + Decimal("1") / Decimal("4.00")
        )

        self.assertAlmostEqual(
            float(result.closing_probability),
            float(expected_probability),
            places=12,
        )
        self.assertAlmostEqual(
            float(result.clv_model_vs_close),
            float(Decimal("0.55") - expected_probability),
            places=12,
        )

    def test_settlement_row_keeps_probability_and_edge_separate(self):
        service = SettlementService(None, None, dry_run=True)

        pick = SettlementInput(
            pick_id="pick-1",
            fixture_id="af-1",
            market="1X2",
            selection="HOME",
            stake_units=Decimal("1"),
            entry_odds=Decimal("2.00"),
            model_probability=Decimal("0.55"),
        )
        result = FixtureResult(
            fixture_id="af-1",
            status_short="FT",
            kickoff_utc="2026-07-01T12:00:00Z",
            home_score=1,
            away_score=0,
        )
        outcome = SettlementOutcome(
            status="WIN",
            actual_outcome="HOME",
            settlement_basis="TEST",
            profit_units=Decimal("1"),
            stake_returned_units=Decimal("1"),
            win_fraction=Decimal("1"),
            loss_fraction=Decimal("0"),
        )
        clv = SimpleNamespace(
            closing_odds=Decimal("2.00"),
            closing_bookmaker="sharpbook",
            closing_snapshot_id="snapshot-1",
            overround=Decimal("1.05"),
            closing_probability=Decimal("0.48"),
            clv_market_movement=Decimal("0.00"),
            clv_model_vs_close=Decimal("0.07"),
            clv_method="NO_VIG_SAME_BOOKMAKER",
            clv_warning=None,
        )

        row = service._build_row({}, None, pick, result, outcome, clv)

        self.assertEqual(row["clv_probability"], 0.48)
        self.assertEqual(row["clv_model_vs_close"], 0.07)

    def test_missing_pick_id_is_skipped(self):
        service = SettlementService(None, None, dry_run=True)

        normalized = service._input_from_pick({
            "pick_id": "",
            "fixture_id": "af-1",
            "status": "VALUE_PICK",
            "market": "1X2",
            "selection": "HOME",
            "stake_units": 1,
            "entry_odds": 2.00,
        })

        self.assertIsInstance(normalized, SettlementOutcome)
        self.assertEqual(
            normalized.settlement_basis,
            "SKIPPED_MISSING_PICK_ID",
        )


    def test_clv_rejects_invalid_complementary_odds_of_one(self):
        result = calculate_clv(
            entry_odds=Decimal("11.00"),
            model_probability=Decimal("0.50"),
            market="BTTS",
            selection="BTTS_YES",
            closing_bookmaker="marathonbet",
            quotes=[
                OddsQuote(
                    "marathonbet",
                    "BTTS",
                    "BTTS_YES",
                    Decimal("11.00"),
                    "yes-valid",
                    "2026-07-15T18:59:10Z",
                ),
                OddsQuote(
                    "marathonbet",
                    "BTTS",
                    "BTTS_NO",
                    Decimal("1.00"),
                    "no-invalid",
                    "2026-07-15T18:59:20Z",
                ),
            ],
        )

        self.assertEqual(result.clv_method, "IMPLIED_FALLBACK")
        self.assertEqual(result.closing_odds, Decimal("11.00"))
        self.assertIsNone(result.overround)
        self.assertEqual(
            result.closing_probability,
            Decimal("1") / Decimal("11.00"),
        )
        self.assertEqual(
            result.clv_warning,
            "MISSING_COMPLEMENTARY_ODDS",
        )

    def test_clv_rejects_invalid_selected_odds_of_one(self):
        result = calculate_clv(
            entry_odds=Decimal("2.00"),
            model_probability=Decimal("0.50"),
            market="BTTS",
            selection="BTTS_YES",
            closing_bookmaker="marathonbet",
            quotes=[
                OddsQuote(
                    "marathonbet",
                    "BTTS",
                    "BTTS_YES",
                    Decimal("1.00"),
                    "yes-invalid",
                    "2026-07-15T18:59:10Z",
                ),
                OddsQuote(
                    "marathonbet",
                    "BTTS",
                    "BTTS_NO",
                    Decimal("2.00"),
                    "no-valid",
                    "2026-07-15T18:59:20Z",
                ),
            ],
        )

        self.assertEqual(result.clv_method, "MISSING_CLOSING_ODDS")
        self.assertIsNone(result.closing_odds)
        self.assertIsNone(result.closing_probability)
        self.assertEqual(
            result.clv_warning,
            "NO_SELECTED_CLOSING_ODDS",
        )


    def test_clv_rejects_invalid_database_row_odds_of_one(self):
        result = calculate_clv(
            entry_odds=Decimal("11.00"),
            model_probability=Decimal("0.50"),
            market="BTTS",
            selection="BTTS_YES",
            closing_bookmaker="marathonbet",
            quotes=[
                {
                    "bookmaker": "marathonbet",
                    "market": "BTTS",
                    "selection": "BTTS_YES",
                    "odds": "11.00",
                    "snapshot_key": "yes-valid-row",
                    "snapshot_timestamp_utc": "2026-07-15T18:59:10Z",
                },
                {
                    "bookmaker": "marathonbet",
                    "market": "BTTS",
                    "selection": "BTTS_NO",
                    "odds": "1.00",
                    "snapshot_key": "no-invalid-row",
                    "snapshot_timestamp_utc": "2026-07-15T18:59:20Z",
                },
            ],
        )

        self.assertEqual(result.clv_method, "IMPLIED_FALLBACK")
        self.assertEqual(result.closing_odds, Decimal("11.00"))
        self.assertIsNone(result.overround)
        self.assertEqual(
            result.closing_probability,
            Decimal("1") / Decimal("11.00"),
        )
        self.assertEqual(
            result.clv_warning,
            "MISSING_COMPLEMENTARY_ODDS",
        )


if __name__ == "__main__":
    unittest.main()
