import os
import unittest
from pathlib import Path
from unittest.mock import patch

from football_agent.scripts import run_settlement


class V2513SettlementWriteGateTests(unittest.TestCase):
    def test_settle_mode_requires_explicit_write_confirmation(self):
        self.assertTrue(
            hasattr(run_settlement, "require_settlement_write_confirmation"),
            "Settlement runner mist een expliciete write-confirmation gate",
        )

        gate = run_settlement.require_settlement_write_confirmation

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SETTLEMENT_WRITE_CONFIRMATION", None)

            with self.assertRaises(SystemExit):
                gate("settle")


    def test_non_settle_modes_do_not_require_confirmation(self):
        gate = run_settlement.require_settlement_write_confirmation

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SETTLEMENT_WRITE_CONFIRMATION", None)

            self.assertIsNone(gate("healthcheck"))
            self.assertIsNone(gate("dry_run"))

    def test_settle_mode_accepts_only_exact_confirmation(self):
        gate = run_settlement.require_settlement_write_confirmation

        with patch.dict(
            os.environ,
            {"SETTLEMENT_WRITE_CONFIRMATION": "wrong-value"},
            clear=False,
        ):
            with self.assertRaises(SystemExit):
                gate("settle")

        with patch.dict(
            os.environ,
            {
                "SETTLEMENT_WRITE_CONFIRMATION":
                    run_settlement.SETTLEMENT_WRITE_CONFIRMATION_VALUE
            },
            clear=False,
        ):
            self.assertIsNone(gate("settle"))

    def test_workflow_forwards_explicit_write_confirmation(self):
        workflow = Path(
            ".github/workflows/settlement-v25.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("write_confirmation:", workflow)
        self.assertIn(
            "SETTLEMENT_WRITE_CONFIRMATION: "
            "${{ github.event.inputs.write_confirmation || '' }}",
            workflow,
        )
        self.assertNotIn(
            'default: "I_UNDERSTAND_SETTLEMENT_WRITES"',
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
