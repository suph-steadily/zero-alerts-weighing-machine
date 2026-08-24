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
    """The NOC weight model, cure split (scratch-darren v8 REPORT.md, 8/19).

    74% of NOCs cure. A cured NOC costs ~0 (book-level, undetectable) to
    -2.1% of that agent's next-year binds per event (within-agent panel);
    weights.noc.cure_price_basis names which basis the config's cured value
    represents. An uncured cancellation costs ~20% of the relationship, and
    the front-loading is in DOSE, not time: the first meaningful cancellation
    does most of the damage (deepening to 25% of book adds little), while
    over time the damage stays flat for 12+ months, a recurring annual flow
    while the relationship stays broken. v0 simplification, flagged: the
    -20% is treated as level per event, which overstates agents with
    several NOCs.
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
    if cfg.mode != "weigh":
        raise ValueError("weigh() takes a weigh-mode config; "
                         "use backtest.score() for mode 'backtest'")
    if tolerance_bar is None:
        tolerance_bar = cfg.tolerance_bar   # config value; CLI flag overrides

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
    # Optional: the v8 agent-side NOE price (REPORT.md:110-117). NOEs also
    # cost future binds from the issuing agent (~-1.3%/event blended).
    noe_agent = cfg.weights.get("noe", {}).get("agent_book_loss_pct")

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

    # The agent-side NOE line, only when the config carries the v8 weight.
    # Priced % x priced NOE count, then x agent book size and bind weight
    # (both unpriced today), so the line stays honestly UNPRICED; the
    # sensitivity block below shows it in binds.
    if noe_agent is not None:
        lines.insert(
            len(lines) - 1,   # before the loss line
            LedgerLine(
                key="noe_agent_attrition", label="NOE cost, agent attrition",
                kind=DOLLARS, good_when="down",
                quantity=d_noe.mul(noe_agent).scaled(0.01)
                              .mul(agent_binds).mul(bind_w).negate(),
                notes="per NOE: %s%% of the issuing agent's next-year binds "
                      "(v8 within-agent panel, ok/cancelled blended). Dollars "
                      "need agent book size AND bind weight; see sensitivity."
                      % noe_agent.fmt(1)))

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
    if dB.is_priced and d_noc.is_priced and d_noc.point and d_noc.point > 0:
        ratio = Quantity(
            point=dB.point / d_noc.point,
            low=(dB.lo / d_noc.hi) if d_noc.hi > 0 else dB.lo / d_noc.point,
            high=(dB.hi / d_noc.lo) if d_noc.lo > 0 else float("inf"),
            unit="binds per NOC", status=d_noc.status,
            source="derived: binds gained / NOCs added (gross, un-weighted)")

    # ---- sensitivity grids (the UNPRICED toggles, never hidden) ----------
    # Every block also names its flip point where one exists: the driver
    # value at which the recommendation changes. Blocks render only when the
    # counts they lean on are priced, so a config with unknown counts still
    # loads and prints honest chips instead of crashing.
    sens = []
    subtotal_q = next((ln.quantity for ln in lines
                       if ln.key == "priced_subtotal"), None)
    if bind_w.sensitivity and dB.is_priced and dB.point:
        rows = [SensitivityRow(
            label="year-one premium $%s per bind" % format(v, ","),
            value=dB.point * v, unit="USD/mo GWP from new binds")
            for v in bind_w.sensitivity]
        flip = ""
        if subtotal_q is not None and subtotal_q.is_priced:
            v_star = -subtotal_q.point / dB.point
            if v_star > 0:
                flip = ("the priced subtotal turns positive at ~$%s year-one "
                        "premium per bind" % format(round(v_star), ","))
            else:
                flip = ("the priced subtotal is already positive before any "
                        "bind value is counted")
        sens.append(SensitivityBlock(
            key="gwp", title="GWP from new binds", driver="bind.year1_premium_usd",
            rows=rows, notes=bind_w.source, flip=flip))
    if (agent_binds.sensitivity and d_noc.is_priced and d_noc.point
            and noc_pct.is_priced and dB.is_priced):
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
        flip = ""
        per_noc_frac = noc_pct.point / 100.0
        if per_noc_frac > 0:
            v_star = dB.point / (d_noc.point * per_noc_frac)
            flip = ("net bind gain hits zero at ~%.0f binds/agent/yr; every "
                    "grid book size below that keeps the trade positive in "
                    "counts" % v_star)
        sens.append(SensitivityBlock(
            key="noc_attrition", title="NOC agent attrition, in binds",
            driver="noc.agent_next_year_binds", rows=rows,
            notes="counts-denominated on purpose: comparable to the bind "
                  "gain without touching the unpriced bind weight. Assumes "
                  "each NOC lands on a distinct agent; the dose "
                  "front-loading (first cancellation does most damage) is "
                  "ignored.", flip=flip))
        if (noe_agent is not None and noe_agent.is_priced
                and d_noe.is_priced and d_noe.point):
            rows = []
            for i, v in enumerate(agent_binds.sensitivity):
                lbl = (agent_binds.sensitivity_labels[i]
                       if i < len(agent_binds.sensitivity_labels)
                       else "%s binds/agent/yr" % v)
                lost = d_noe.point * (noe_agent.point / 100.0) * v
                rows.append(SensitivityRow(
                    label=lbl, value=lost,
                    unit="binds-equivalent/mo lost to NOE agent attrition "
                         "(net bind gain %.0f)" % (dB.point - lost)))
            flip = ""
            if noe_agent.point > 0:
                v_star = dB.point / (d_noe.point * noe_agent.point / 100.0)
                flip = ("net bind gain hits zero at ~%.0f binds/agent/yr on "
                        "the NOE side alone" % v_star)
            sens.append(SensitivityBlock(
                key="noe_agent_attrition", title="NOE agent attrition, in binds",
                driver="noc.agent_next_year_binds", rows=rows,
                notes=noe_agent.source, flip=flip))
    if noe_exp.sensitivity and d_noe.is_priced and d_noe.point:
        rows = [SensitivityRow(
            label="$%s experience cost per NOE" % format(v, ","),
            value=-d_noe.point * v, unit="USD/mo")
            for v in noe_exp.sensitivity]
        flip = ""
        if labor_saved.is_priced and labor_saved.point > 0:
            v_star = labor_saved.point / d_noe.point
            flip = ("no zero crossing (this line only subtracts); at ~$%s "
                    "per NOE it alone would swallow the review-labor savings"
                    % format(round(v_star), ","))
        sens.append(SensitivityBlock(
            key="noe_exp", title="NOE customer-experience cost",
            driver="noe.experience_cost_usd", rows=rows, notes=noe_exp.source,
            flip=flip))

    # ---- caveats ---------------------------------------------------------
    caveats = list(cfg.notes)
    if noc_floor is not None:
        caveats.append(
            "Selection-effect floor: at the projected un-reviewed rate "
            "(%s per 100) the NOC line becomes %s per month. The headline "
            "uses the measured twin and is therefore a floor."
            % (floor.fmt(1), noc_floor.fmt(0, signed=True)))
    # After-the-levers scenario: the automation-coverage input. If the
    # levers (pre-fill, roof retargeting, attestations) duplicate the
    # addressable share of the NOC gap, removal is weighed AFTER they land.
    levers = cfg.counts.get("levers_addressable_share_of_noc_gap")
    if (levers is not None and levers.is_priced
            and d_noc.is_priced and d_noc.point is not None):
        kept = Quantity(point=1 - levers.point,
                        low=1 - levers.hi, high=1 - levers.lo,
                        status=levers.status,
                        source="derived (1 - addressable share)")
        gap_after = noc_twin.sub(noc_rev).mul(kept)
        rate_after = noc_rev.add(gap_after)
        d_noc_after = (B0.mul(gap_after).scaled(0.01)
                       .add(dB.mul(rate_after).scaled(0.01)))
        caveats.append(
            "After-the-levers scenario: if the levers duplicate the "
            "addressable share of the NOC gap (%s of it), the NOC line "
            "becomes %s per month instead of %s. Weigh removal after the "
            "levers land, not instead of them."
            % (levers.fmt(2), d_noc_after.fmt(1, signed=True),
               d_noc.fmt(1, signed=True)))
    caveats.append(
        "Name your NOC denominator: every rate above is per 100 BOUND "
        "policies of this cohort, inspection-lane NOCs, first 90 days. "
        "Darren's 11.7% is every UW NOC, book-wide. Never mix them.")
    caveats.append(
        "Counts estimated via %s. Never compare this ledger against one "
        "built on a different estimation method without saying so; the "
        "methods have different blind spots (REQUIREMENTS.md, Estimation "
        "methods)." % cfg.estimator_label)
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
        caveats=caveats, bind_to_noc_ratio=ratio, tolerance_bar=tolerance_bar,
        estimator_label=cfg.estimator_label,
        comparison=cfg.estimator.get("comparison", ""),
        noc_cure_price_basis=cfg.noc_cure_price_basis)

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
