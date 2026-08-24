"""The Phase 1 hardening pass: named cure price, tolerance bar comparison,
flip points, the v8 agent-side NOE weight, the after-the-levers scenario,
loader errors that speak plainly, and the machine running on a config whose
counts are still unknown (chips, not crashes)."""

import copy
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weighing_machine import Quantity, load, weigh

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DWELLING = os.path.join(HERE, "configs", "dwelling_age.json")


def _dump_tmp(raw):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(raw, f)
    f.close()
    return f.name


class _WithRaw(unittest.TestCase):
    def setUp(self):
        with open(DWELLING) as f:
            self.raw = json.load(f)

    def _load_raw(self, raw):
        path = _dump_tmp(raw)
        try:
            return load(path)
        finally:
            os.unlink(path)

    def _assert_load_raises(self, raw, pattern):
        path = _dump_tmp(raw)
        try:
            with self.assertRaisesRegex(ValueError, pattern):
                load(path)
        finally:
            os.unlink(path)


class TestNamedCurePrice(_WithRaw):
    def test_dwelling_declares_book_basis(self):
        cfg = load(DWELLING)
        self.assertEqual(cfg.noc_cure_price_basis, "book")

    def test_missing_basis_is_rejected(self):
        raw = copy.deepcopy(self.raw)
        del raw["weights"]["noc"]["cure_price_basis"]
        self._assert_load_raises(raw, "cure_price_basis")

    def test_unknown_basis_is_rejected(self):
        raw = copy.deepcopy(self.raw)
        raw["weights"]["noc"]["cure_price_basis"] = "vibes"
        self._assert_load_raises(raw, "cure_price_basis")

    def test_ledger_prints_the_basis(self):
        text = weigh(load(DWELLING)).to_text()
        self.assertIn("Cured-NOC price basis: book", text)


class TestLoaderHardening(_WithRaw):
    def test_missing_weight_key_fails_plainly(self):
        raw = copy.deepcopy(self.raw)
        del raw["weights"]["review"]["labor_usd_per_review"]
        self._assert_load_raises(raw, "missing weight keys.*review.labor_usd_per_review")

    def test_unpriced_cure_rate_is_rejected(self):
        raw = copy.deepcopy(self.raw)
        raw["weights"]["noc"]["cure_rate"] = {
            "status": "unpriced", "source": "pretend nobody measured it"}
        self._assert_load_raises(raw, "cure_rate must be priced")

    def test_comment_keys_are_tolerated_inside_counts_and_weights(self):
        raw = copy.deepcopy(self.raw)
        raw["counts"]["_comment"] = "a note, not a Quantity"
        raw["weights"]["noc"]["_comment"] = "same here"
        cfg = self._load_raw(raw)
        self.assertNotIn("_comment", cfg.counts)
        self.assertNotIn("_comment", cfg.weights["noc"])

    def test_denominator_rule_catches_per_100_units_too(self):
        with self.assertRaisesRegex(ValueError, "denominator"):
            Quantity.from_json({"point": 5.0, "unit": "NOCs per 100 bound"},
                               key="sneakily_named_rate")


class TestToleranceBar(_WithRaw):
    def test_config_bar_flows_to_verdict(self):
        raw = copy.deepcopy(self.raw)
        raw["alert"]["tolerance_bar"] = 3.0
        ledger = weigh(self._load_raw(raw))
        self.assertIn("PASS", ledger.tolerance_verdict())   # rate ~4.8 vs 3.0

    def test_cli_style_bar_overrides_and_fails(self):
        ledger = weigh(load(DWELLING), tolerance_bar=100.0)
        v = ledger.tolerance_verdict()
        self.assertIn("FAIL", v)                            # 4.8 vs 100

    def test_straddle_is_flagged(self):
        # bar 3.0 sits inside the [1.0 .. 95.4] range: verdict not settled.
        ledger = weigh(load(DWELLING), tolerance_bar=3.0)
        self.assertIn("straddles", ledger.tolerance_verdict())

    def test_no_bar_stays_not_set(self):
        ledger = weigh(load(DWELLING))
        self.assertIn("NOT SET", ledger.tolerance_verdict())

    def test_invalid_bar_rejected(self):
        raw = copy.deepcopy(self.raw)
        raw["alert"]["tolerance_bar"] = -2
        self._assert_load_raises(raw, "tolerance_bar")


class TestFlipPoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = weigh(load(DWELLING))
        cls.blocks = {b.key: b for b in cls.ledger.sensitivities}

    def test_gwp_flip_is_about_109_per_bind(self):
        # priced subtotal ~ -$12.6k / 115 binds ~= $109 of year-one premium
        self.assertIn("109", self.blocks["gwp"].flip)

    def test_noc_attrition_flip_is_about_81_binds_per_agent(self):
        self.assertIn("81", self.blocks["noc_attrition"].flip)
        self.assertIn("hits zero", self.blocks["noc_attrition"].flip)

    def test_noe_exp_flip_names_the_labor_anchor(self):
        self.assertIn("swallow", self.blocks["noe_exp"].flip)

    def test_flips_render_in_text(self):
        self.assertIn("flip point", self.ledger.to_text())


class TestNoeAgentSide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = weigh(load(DWELLING))

    def test_line_exists_and_is_unpriced(self):
        ln = self.ledger.line("noe_agent_attrition")
        self.assertFalse(ln.quantity.is_priced)
        self.assertIn("v8", ln.notes)

    def test_sensitivity_block_exists(self):
        keys = [b.key for b in self.ledger.sensitivities]
        self.assertIn("noe_agent_attrition", keys)


class TestAfterTheLevers(unittest.TestCase):
    def test_scenario_caveat_present_and_smaller(self):
        ledger = weigh(load(DWELLING))
        caveat = [c for c in ledger.caveats if "After-the-levers" in c]
        self.assertEqual(len(caveat), 1)
        # 76% of the gap addressed cuts the NOC line roughly in half or better
        self.assertIn("+9.7", caveat[0])
        self.assertIn("+23.9", caveat[0])


class TestUnknownCountsStillRun(_WithRaw):
    def test_roof_style_config_weighs_with_chips(self):
        raw = copy.deepcopy(self.raw)
        # Blank out what a brand-new alert would not know yet.
        unknown = {"status": "unpriced", "confidence": "none",
                   "source": "not pulled yet"}
        for k in ("current_binds_per_month", "binds_gained_per_month"):
            raw["counts"][k] = dict(unknown, unit="per month")
        for k in ("reviewed_noc_per_100_bound_90d", "twin_noc_per_100_bound_90d",
                  "reviewed_noe_per_100_bound_90d", "twin_noe_per_100_bound_90d",
                  "foregone_uw_correction_premium_per_100_bound_usd"):
            raw["counts"][k] = dict(unknown, unit="per 100 bound",
                                    denominator="per 100 bound policies, "
                                                "window to be defined")
        raw["counts"].pop("unreviewed_noc_projection_per_100", None)
        raw["counts"].pop("levers_addressable_share_of_noc_gap", None)
        ledger = weigh(self._load_raw(raw))
        self.assertIsNone(ledger.bind_to_noc_ratio)
        self.assertFalse(ledger.line("nocs").quantity.is_priced)
        text = ledger.to_text()
        self.assertIn("UNPRICED", text)   # chips, not crashes


if __name__ == "__main__":
    unittest.main()
