"""The machine must work for ANY alert, not just dwelling age.

Covers: the estimator declaration (every config says which method produced
its numbers), the backtest mode (water claims, the case we already lived
through), and the guardrails that keep the two modes and five methods from
being silently mixed up.
"""

import copy
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

from weighing_machine import __main__ as cli
from weighing_machine.backtest import score
from weighing_machine.config import ESTIMATORS, load
from weighing_machine.model import weigh

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DWELLING = os.path.join(HERE, "configs", "dwelling_age.json")
WATER = os.path.join(HERE, "configs", "water_claims_backtest.json")
QUEUE = os.path.join(HERE, "configs", "alert_queue.json")


def _dump_tmp(raw):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(raw, f)
    f.close()
    return f.name


class TestEstimatorDeclaration(unittest.TestCase):
    def setUp(self):
        with open(DWELLING) as f:
            self.raw = json.load(f)

    def test_dwelling_declares_sister_cohort(self):
        cfg = load(DWELLING)
        self.assertEqual(cfg.estimator_method, "sister_cohort")
        self.assertIn("sister_cohort", cfg.estimator_label)
        self.assertTrue(cfg.estimator.get("comparison"))

    def test_config_without_estimator_is_rejected(self):
        raw = copy.deepcopy(self.raw)
        del raw["estimator"]
        path = _dump_tmp(raw)
        try:
            with self.assertRaisesRegex(ValueError, "estimator"):
                load(path)
        finally:
            os.unlink(path)

    def test_unknown_method_is_rejected(self):
        raw = copy.deepcopy(self.raw)
        raw["estimator"]["method"] = "vibes"
        path = _dump_tmp(raw)
        try:
            with self.assertRaisesRegex(ValueError, "estimator.method"):
                load(path)
        finally:
            os.unlink(path)

    def test_comparison_text_is_required(self):
        raw = copy.deepcopy(self.raw)
        raw["estimator"].pop("comparison")
        path = _dump_tmp(raw)
        try:
            with self.assertRaisesRegex(ValueError, "comparison"):
                load(path)
        finally:
            os.unlink(path)

    def test_all_five_methods_load(self):
        for method in ESTIMATORS:
            raw = copy.deepcopy(self.raw)
            raw["estimator"] = {"method": method, "comparison": "test setup"}
            path = _dump_tmp(raw)
            try:
                cfg = load(path)
                self.assertEqual(cfg.estimator_method, method)
            finally:
                os.unlink(path)

    def test_ledger_names_the_method(self):
        ledger = weigh(load(DWELLING))
        self.assertIn("sister_cohort", ledger.estimator_label)
        text = ledger.to_text()
        self.assertIn("Counts estimated via", text)
        self.assertTrue(any("different estimation method" in c
                            for c in ledger.caveats))


class TestWaterBacktest(unittest.TestCase):
    def setUp(self):
        self.cfg = load(WATER)

    def test_loads_as_backtest(self):
        self.assertEqual(self.cfg.mode, "backtest")
        self.assertEqual(self.cfg.direction, "automate")
        self.assertEqual(self.cfg.estimator_method, "state_rollout")
        self.assertEqual(len(self.cfg.backtest_claims), 5)

    def test_scorecard_verdicts(self):
        card = score(self.cfg)
        self.assertEqual(card.held, 4)
        self.assertEqual(card.missed, 0)
        self.assertEqual(card.pending, 1)
        pending = [c for c in self.cfg.backtest_claims if c.verdict == "pending"]
        self.assertEqual(pending[0].key, "post_bind_outcomes")
        self.assertFalse(pending[0].actual.is_priced)

    def test_scorecard_text_is_plain_and_complete(self):
        text = score(self.cfg).to_text()
        self.assertIn("Did the automation duplicate the underwriter?", text)
        self.assertIn("4 held / 0 missed / 1 not yet readable", text)
        self.assertIn("11.9", text)          # referral rate actual
        self.assertIn("NOT YET READABLE", text)
        self.assertIn("state_rollout", text)

    def test_wrong_mode_functions_refuse(self):
        with self.assertRaisesRegex(ValueError, "weigh-mode"):
            weigh(self.cfg)
        with self.assertRaisesRegex(ValueError, "backtest-mode"):
            score(load(DWELLING))

    def test_unreadable_actual_cannot_claim_held(self):
        with open(WATER) as f:
            raw = json.load(f)
        for c in raw["backtest"]["claims"]:
            if c["key"] == "post_bind_outcomes":
                c["verdict"] = "held"
        path = _dump_tmp(raw)
        try:
            with self.assertRaisesRegex(ValueError, "pending"):
                load(path)
        finally:
            os.unlink(path)

    def test_backtest_direction_must_be_automate(self):
        with open(WATER) as f:
            raw = json.load(f)
        raw["alert"]["direction"] = "remove"
        path = _dump_tmp(raw)
        try:
            with self.assertRaisesRegex(ValueError, "automate"):
                load(path)
        finally:
            os.unlink(path)


class TestCliBothConfigs(unittest.TestCase):
    def _run(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = cli.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def test_cli_weighs_dwelling(self):
        rc, out, _ = self._run(DWELLING)
        self.assertEqual(rc, 0)
        self.assertIn("THE WEIGHING MACHINE", out)
        self.assertIn("Counts estimated via", out)

    def test_cli_scores_water(self):
        rc, out, _ = self._run(WATER, "--json")
        self.assertEqual(rc, 0)
        self.assertIn("backtest scorecard", out)
        self.assertIn('"held": 4', out)


class TestAlertQueue(unittest.TestCase):
    def test_queue_is_valid_and_dwelling_age_leads(self):
        with open(QUEUE) as f:
            q = json.load(f)
        rows = q["queue"]
        self.assertGreaterEqual(len(rows), 7)
        vols = [r["uw_touches_per_month"] for r in rows[:7]]
        self.assertEqual(vols, sorted(vols, reverse=True))
        self.assertEqual(rows[0]["alert_family"], "dwelling age")
        self.assertEqual(rows[0]["uw_touches_per_month"], 5044)
        for r in rows:
            for k in ("alert_family", "uw_touches_per_month", "comparison_group",
                      "uw_action_mix", "post_bind_outcomes", "levers", "status"):
                self.assertIn(k, r, "queue row missing %s" % k)


if __name__ == "__main__":
    unittest.main()
