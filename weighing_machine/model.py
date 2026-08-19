"""Core trade-off math: turn an alert config into a Ledger.

The forecast model (direction "remove"; "add" is the exact negation):

  binds gained    dB   = pinned (v0: twin layering, +115 [50..175]/mo)
  book NOC shift       = B0 x (twin_noc - reviewed_noc) / 100
  new-bind NOCs        = dB x twin_noc / 100
  NOCs added      dNOC = book shift + new-bind NOCs
  NOEs added      dNOE = same shape with the NOE rates
                         (the v0 hand ledger's "+30" counted ONLY the book
                         shift; the machine reports that component separately
                         so v0 stays reproducible, plus the coherent total)
  reviews freed        = pinned forced reviews per month
  premium foregone     = B0 x foregone_per_100_bound / 100

  where B0 = current binds/month of the gated cohort.

Weights applied where priced:
  * freed review  -> reviews x labor_usd_per_review           (partial)
  * UW-correction premium                                     (measured)
  * NOC agent side -> cure split (scratch-darren tradeoff.py spirit):
        per-NOC agent-book loss % = cure x cured_loss + (1 - cure) x uncured_loss
    then binds-equivalent via the agent_next_year_binds sensitivity grid.
  * bind, NOE experience, loss join -> UNPRICED, sensitivity grids only.

Everything is worst-case interval arithmetic on Quantity; see quantity.py.
Pure python, stdlib only.
"""

from __future__ import annotations

from typing import Optional

from .config import AlertConfig
from .ledger import (COUNT, DOLLARS, Ledger, LedgerLine, SensitivityBlock,
                     SensitivityRow)
from .quantity import PARTIAL, UNPRICED, Quantity


def per_noc_agent_book_loss_pct(cfg: AlertConfig) -> Quantity:
    """The NOC weight model, cure split (Darren's curves, scratch-darren Aug 18).

    74% of NOCs cure; a cured one costs ~0 to -2% of that agent's next-year
    binds per event; an uncured cancellation costs ~20%, front-loaded.
    v0 simplification, flagged: the -20% is treated as level per event
    (front-loading and multi-NOC saturation ignored; overstates for agents
    with several NOCs).
    """
    cure = cfg.weight("noc", "cure_rate")
    cured = cfg.weight("noc", "cured_agent_book_loss_pct")
    uncured = cfg.weight("noc", "uncured_agent_book_loss_pct")
    one_minus_cure = Quantity(point=1 - cure.point, low=1 - cure.hi, high=1 - cure.lo,
                              status=cure.status, source="derived (1 - cure_rate)")
    q = cure.mul(cured).add(one_minus_cure.mul(uncured))
    return Quantity(point=q.point, low=q.lo, high=q.hi,
                    unit="% of that agent's next-year binds, per NOC",
                    status=PARTIAL,
                    source="cure split over scratch-darren curves: "
                           "cure x cured_loss + (1-cure) x uncured_loss")


def _rate_shift(binds: Quantity, rate_after: Quantity, rate_before: Quantity) -> Quantity:
    """binds x (rate_after - rate_before) / 100, interval-propagated."""
    return binds.mul(rate_after.sub(rate_before)).scaled(0.01)


def weigh(cfg: AlertConfig, scale: float = 1.0,
          tolerance_bar: Optional[float] = None) -> Ledger:
    """Run the machine. `scale` linearly shrinks/grows the volume inputs
    (e.g. 0.93 for the top-7-states cut, 0.5 for a 50% holdout). Rates are
    per-100 and do not scale. `tolerance_bar` is LaNae's accepted
    binds-per-NOC exchange rate, once she has been asked."""
    if scale <= 0:
        raise ValueError("scale must be positive")

    # Volume inputs (scale applies).
    B0 = cfg.count("current_binds_per_month").scaled(scale)
    dB = cfg.count("binds_gained_per_month").scaled(scale)
    reviews = cfg.count("forced_reviews_per_month").scaled(scale)

    # Rates (scale does not apply).
    noc_rev = cfg.count("reviewed_noc_per_100_bound_90d")
    noc_twin = cfg.count("twin_noc_per_100_bound_90d")
    noe_rev = cfg.count("reviewed_noe_per_100_bound_90d")
    noe_twin = cfg.count("twin_noe_per_100_bound_90d")
    prem_100 = cfg.count("foregone_uw_correction_premium_per_100_bound_usd")

    # ---- counts ---------------------------------------------------------
    noc_book = _rate_shift(B0, noc_twin, noc_rev)
    noc_new = dB.mul(noc_twin).scaled(0.01)
    d_noc = noc_book.add(noc_new)

    noe_book = _rate_shift(B0, noe_twin, noe_rev)   # the v0-comparable "+30"
    noe_new = dB.mul(noe_twin).scaled(0.01)
    d_noe = noe_book.add(noe_new)

    reviews_delta = reviews.negate()                # removal frees them

    # Selection-effect floor scenario: the twin rate understates true
    # un-reviewed 101+ (book is older than the twin; ramp +22.8%/decade).
    floor = cfg.counts.get("unreviewed_noc_projection_per_100")
    noc_floor = None
    if floor is not None and floor.is_priced:
        noc_floor = _rate_shift(B0, floor, noc_rev).add(dB.mul(floor).scaled(0.01))

    # ---- dollars --------------------------------------------------------
    prem_delta = B0.mul(prem_100).scaled(0.01).negate()   # foregone: a loss
    labor = cfg.weight("review", "labor_usd_per_review")
    labor_saved = reviews.mul(labor)                       # freed = a gain

    noc_pct = per_noc_agent_book_loss_pct(cfg)

    bind_w = cfg.weight("bind", "year1_premium_usd")
    agent_binds = cfg.weight("noc", "agent_next_year_binds")
    noe_exp = cfg.weight("noe", "experience_cost_usd")
    noe_relief = cfg.weight("noe", "customer_premium_relief_usd")
    loss_join = cfg.weight("loss", "loss_join_usd")

    lines = [
        LedgerLine(
            key="binds", label="Bound policies", kind=COUNT, good_when="up",
            quantity=dB,
            notes="quotes that die at the wall today"),
        LedgerLine(
            key="forced_reviews", label="Forced UW reviews", kind=COUNT,
            good_when="down", quantity=reviews_delta,
            notes="work that stops existing"),
        LedgerLine(
            key="nocs", label="NOCs (90d, per bound cohort)", kind=COUNT,
            good_when="down", quantity=d_noc,
            components={"book shifts to twin rate": noc_book,
                        "new binds at twin rate": noc_new},
            notes="floor, not estimate: twin never faced the alert"),
        LedgerLine(
            key="noes", label="UW corrective endorsements (90d)", kind=COUNT,
            good_when="down", quantity=d_noe,
            components={"book shifts to twin rate (v0's +30)": noe_book,
                        "new binds at twin rate (v0 omitted)": noe_new},
            notes="~90% exclusion changes; roof-surfacing exclusion alone is "
                  "53-59% of UW NOEs"),
        LedgerLine(
            key="uw_correction_premium", label="Premium from UW corrections",
            kind=DOLLARS, good_when="up", quantity=prem_delta,
            notes="bound-only, deliberately; fixes raise price 3.4x more "
                  "often than they lower it; ~0% recovered at renewal"),
        LedgerLine(
            key="review_labor_saved", label="UW review labor saved",
            kind=DOLLARS, good_when="up", quantity=labor_saved,
            notes="per-review rate is our division of the expense-model pool; "
                  "see input note"),
        LedgerLine(
            key="gwp_new_binds", label="GWP from new binds", kind=DOLLARS,
            good_when="up",
            quantity=dB.mul(bind_w),      # bind weight UNPRICED -> stays UNPRICED
            notes="bind weight is year-one premium at best; LTV unpriced. "
                  "See sensitivity."),
        LedgerLine(
            key="noc_agent_attrition", label="NOC cost, agent attrition",
            kind=DOLLARS, good_when="down",
            # % -> fraction via scaled(0.01); UNPRICED inputs keep it UNPRICED
            quantity=d_noc.mul(noc_pct).scaled(0.01)
                          .mul(agent_binds).mul(bind_w).negate(),
            notes="per NOC: %s%% of the issuing agent's next-year binds "
                  "(cure split). Dollars need agent book size AND bind "
                  "weight; see sensitivity." % noc_pct.fmt(1)),
        LedgerLine(
            key="noe_cost", label="NOE cost, customer side", kind=DOLLARS,
            good_when="down",
            quantity=d_noe.mul(noe_exp).negate(),   # UNPRICED until exp is priced
            notes="premium side measured at ~$%d relief per event; the "
                  "removed-coverage / bait-and-switch side is the unpriced "
                  "half" % (noe_relief.point or 0)),
        LedgerLine(
            key="loss_impact", label="Effect on loss ratio", kind=DOLLARS,
            good_when="unknown", quantity=loss_join,
            notes="the line that decides it; lands ~1 year later. Plan: "
                  "actuarial backtest of the twin's on-book losses."),
    ]

    # Priced subtotal: only the dollar lines that actually carry a price.
    # Never the verdict while anything above is UNPRICED; the caveat says so.
    priced = [ln.quantity for ln in lines
              if ln.kind == DOLLARS and ln.quantity.is_priced]
    if priced:
        subtotal = priced[0]
        for q in priced[1:]:
            subtotal = subtotal.add(q)
        n_unpriced = sum(1 for ln in lines
                         if ln.kind == DOLLARS and not ln.quantity.is_priced)
        lines.append(LedgerLine(
            key="priced_subtotal",
            label="Priced subtotal (%d dollar lines still unpriced)" % n_unpriced,
            kind=DOLLARS, good_when="up", quantity=subtotal,
            notes="sum of the priced dollar lines only. NOT the verdict: the "
                  "biggest lines (binds, NOC attrition, loss) are unpriced."))

    # ---- exchange rate ---------------------------------------------------
    ratio = None
    if d_noc.point and d_noc.point > 0:
        ratio = Quantity(
            point=dB.point / d_noc.point,
            low=(dB.lo / d_noc.hi) if d_noc.hi > 0 else dB.lo / d_noc.point,
            high=(dB.hi / d_noc.lo) if d_noc.lo > 0 else float("inf"),
            unit="binds per NOC", status=d_noc.status,
            source="derived: binds gained / NOCs added (gross, un-weighted)")

    # ---- sensitivity grids (the UNPRICED toggles, never hidden) ----------
    sens = []
    if bind_w.sensitivity:
        rows = [SensitivityRow(
            label="year-one premium $%s per bind" % format(v, ","),
            value=dB.point * v, unit="USD/mo GWP from new binds")
            for v in bind_w.sensitivity]
        sens.append(SensitivityBlock(
            key="gwp", title="GWP from new binds", driver="bind.year1_premium_usd",
            rows=rows, notes=bind_w.source))
    if agent_binds.sensitivity:
        rows = []
        for i, v in enumerate(agent_binds.sensitivity):
            lbl = (agent_binds.sensitivity_labels[i]
                   if i < len(agent_binds.sensitivity_labels)
                   else "%s binds/agent/yr" % v)
            lost = d_noc.point * (noc_pct.point / 100.0) * v
            rows.append(SensitivityRow(
                label=lbl, value=lost,
                unit="binds-equivalent/mo lost to agent attrition "
                     "(net bind gain %.0f)" % (dB.point - lost)))
        sens.append(SensitivityBlock(
            key="noc_attrition", title="NOC agent attrition, in binds",
            driver="noc.agent_next_year_binds", rows=rows,
            notes="counts-denominated on purpose: comparable to the bind "
                  "gain without touching the unpriced bind weight. Assumes "
                  "each NOC lands on a distinct agent; front-loading ignored."))
    if noe_exp.sensitivity:
        rows = [SensitivityRow(
            label="$%s experience cost per NOE" % format(v, ","),
            value=-d_noe.point * v, unit="USD/mo")
            for v in noe_exp.sensitivity]
        sens.append(SensitivityBlock(
            key="noe_exp", title="NOE customer-experience cost",
            driver="noe.experience_cost_usd", rows=rows, notes=noe_exp.source))

    # ---- caveats ---------------------------------------------------------
    caveats = list(cfg.notes)
    if noc_floor is not None:
        caveats.append(
            "Selection-effect floor: at the projected un-reviewed rate "
            "(%s per 100) the NOC line becomes %s per month. The headline "
            "uses the measured twin and is therefore a floor."
            % (floor.fmt(1), noc_floor.fmt(0, signed=True)))
    caveats.append(
        "Name your NOC denominator: every rate above is per 100 BOUND "
        "policies of this cohort, inspection-lane NOCs, first 90 days. "
        "Darren's 11.7% is every UW NOC, book-wide. Never mix them.")
    caveats.append(
        "Ranges are worst-case interval propagation, so they are wider than "
        "any single hand-computed bracket; a hand range should sit inside "
        "the machine's range.")
    unpriced_labels = [ln.label for ln in lines if not ln.quantity.is_priced]
    if unpriced_labels:
        caveats.append(
            "The priced dollar lines are NOT the verdict: still unpriced -> %s."
            % "; ".join(unpriced_labels))

    ledger = Ledger(
        alert_id=cfg.alert_id, alert_name=cfg.name, direction=cfg.direction,
        as_of=cfg.as_of, scale=scale, lines=lines, sensitivities=sens,
        caveats=caveats, bind_to_noc_ratio=ratio, tolerance_bar=tolerance_bar)

    # Direction "add": a proposed new alert is the mirror image, so every
    # delta flips sign (adding the gate loses the binds, saves the NOCs,
    # creates the reviews, captures the premium).
    if cfg.direction == "add":
        for ln in ledger.lines:
            ln.quantity = ln.quantity.negate()
            ln.components = {k: v.negate() for k, v in ln.components.items()}
        for blk in ledger.sensitivities:
            for row in blk.rows:
                row.value = -row.value

    return ledger
