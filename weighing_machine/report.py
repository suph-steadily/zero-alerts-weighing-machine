"""Self-contained HTML report for one weighed alert.

No external assets, no scripts, system fonts only: the file opens anywhere
and can be screenshotted into a doc. Written for a PM reader: counts first,
dollars where priced, UNPRICED chips instead of hidden guesses, and every
input traceable to its source in the appendix.
"""

from __future__ import annotations

import html

from .config import AlertConfig
from .ledger import COUNT, DOLLARS, Ledger
from .quantity import Quantity

_CSS = """
:root {
  --ink: #1c2733; --muted: #5c6b7a; --line: #dde4ea; --bg: #f6f8fa;
  --card: #ffffff; --good: #1a7f4b; --bad: #b3373d; --warn: #8a6d1a;
  --chip-measured: #e3f2e9; --chip-measured-ink: #1a7f4b;
  --chip-partial: #fdf3d7; --chip-partial-ink: #8a6d1a;
  --chip-unpriced: #fbe4e6; --chip-unpriced-ink: #b3373d;
}
* { box-sizing: border-box; }
body { margin: 0; padding: 2rem 1rem 4rem; background: var(--bg); color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
.wrap { max-width: 860px; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 .2rem; }
h2 { font-size: 1.05rem; text-transform: uppercase; letter-spacing: .06em;
  color: var(--muted); margin: 2.2rem 0 .7rem; }
.sub { color: var(--muted); margin-bottom: 1.4rem; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  padding: 1rem 1.2rem; margin-bottom: 1rem; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: .45rem .6rem; border-bottom: 1px solid var(--line);
  vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: .8rem; text-transform: uppercase;
  letter-spacing: .05em; }
tr:last-child td { border-bottom: none; }
td.num { font-variant-numeric: tabular-nums; white-space: nowrap; font-weight: 600; }
.range { color: var(--muted); font-weight: 400; font-size: .85em; }
.good { color: var(--good); } .bad { color: var(--bad); } .neutral { color: var(--ink); }
.chip { display: inline-block; padding: .05rem .5rem; border-radius: 99px;
  font-size: .72rem; font-weight: 700; letter-spacing: .04em; }
.chip.measured { background: var(--chip-measured); color: var(--chip-measured-ink); }
.chip.partial { background: var(--chip-partial); color: var(--chip-partial-ink); }
.chip.unpriced { background: var(--chip-unpriced); color: var(--chip-unpriced-ink); }
.note { color: var(--muted); font-size: .85rem; }
.banner { border-left: 4px solid var(--warn); background: #fffaf0; padding: .7rem 1rem;
  border-radius: 6px; margin-bottom: 1rem; font-size: .92rem; }
.exch { font-size: 1.15rem; font-weight: 700; }
ul { margin: .3rem 0 .3rem 1.2rem; padding: 0; }
li { margin-bottom: .35rem; }
.small { font-size: .82rem; color: var(--muted); }
footer { margin-top: 2.5rem; color: var(--muted); font-size: .8rem; }
"""


def _esc(s) -> str:
    return html.escape(str(s))


def _chip(status: str) -> str:
    return '<span class="chip %s">%s</span>' % (status, status.upper())


def _fmt_qty(q: Quantity, decimals=0, prefix="") -> str:
    if not q.is_priced:
        return _chip("unpriced")
    cls = "neutral"
    body = q.fmt(decimals, signed=True, prefix=prefix)
    if q.has_range:
        # split "point  [lo .. hi]" so the range renders smaller
        point, rng = body.split("  ", 1)
        return '<span class="%s">%s</span> <span class="range">%s</span>' % (
            cls, _esc(point), _esc(rng))
    return '<span class="%s">%s</span>' % (cls, _esc(body))


def _goodbad(line) -> str:
    q = line.quantity
    if not q.is_priced or q.point == 0 or line.good_when == "unknown":
        return ""
    up = q.point > 0
    win = (up and line.good_when == "up") or (not up and line.good_when == "down")
    return '<span class="%s">%s</span>' % ("good" if win else "bad",
                                           "gain" if win else "cost")


def _ledger_table(lines, decimals=0, prefix="") -> str:
    rows = []
    for ln in lines:
        comp = ""
        if ln.components:
            comp = "<br>".join(
                '<span class="small">%s: %s</span>'
                % (_esc(k), _esc(v.fmt(1, signed=True, prefix=prefix)))
                for k, v in ln.components.items())
        note = ('<div class="note">%s</div>' % _esc(ln.notes)) if ln.notes else ""
        rows.append(
            "<tr><td><strong>%s</strong>%s%s</td><td class='num'>%s</td>"
            "<td>%s</td><td>%s</td></tr>"
            % (_esc(ln.label), note, ("<div>%s</div>" % comp) if comp else "",
               _fmt_qty(ln.quantity, decimals, prefix),
               _goodbad(ln), _chip(ln.status)))
    return ("<table><tr><th>Line</th><th>Change / month</th><th></th>"
            "<th>Status</th></tr>%s</table>" % "".join(rows))


def render_html(ledger: Ledger, cfg: AlertConfig) -> str:
    L = ledger
    parts = []
    parts.append('<div class="wrap">')
    parts.append("<h1>The Weighing Machine: %s</h1>" % _esc(L.alert_name))
    parts.append('<div class="sub">Direction: <strong>%s</strong> the alert &middot; '
                 "scale %.2f &middot; inputs as of %s</div>"
                 % (_esc(L.direction), L.scale, _esc(L.as_of)))
    method_bits = []
    if L.estimator_label:
        method_bits.append("Counts estimated via <strong>%s</strong>"
                           % _esc(L.estimator_label))
    if L.comparison:
        method_bits.append(_esc(L.comparison))
    if L.noc_cure_price_basis:
        method_bits.append("cured-NOC price basis: <strong>%s</strong>"
                           % _esc(L.noc_cure_price_basis))
    if method_bits:
        parts.append('<div class="sub small">%s</div>' % " &middot; ".join(method_bits))

    unpriced = L.unpriced()
    parts.append('<div class="banner"><strong>The machine cannot net this yet.</strong> '
                 "%d dollar lines are still unpriced (%s). Counts are the "
                 "denomination; dollars appear only where a weight exists. "
                 "Never quote the priced subtotal as the verdict.</div>"
                 % (len(unpriced), _esc(", ".join(ln.label for ln in unpriced))))

    parts.append("<h2>Counts, per month</h2>")
    parts.append('<div class="card">%s</div>' % _ledger_table(L.counts(), decimals=0))

    if L.bind_to_noc_ratio is not None:
        parts.append('<div class="card"><div class="exch">Exchange rate: %s binds '
                     "bought per NOC added</div><div class='note'>gross and "
                     "un-weighted; the decision rule compares this against the "
                     "tolerance bar. %s</div></div>"
                     % (_esc(L.bind_to_noc_ratio.fmt(1)),
                        _esc(L.tolerance_verdict())))

    parts.append("<h2>Dollars, per month, where priced</h2>")
    parts.append('<div class="card">%s</div>'
                 % _ledger_table(L.dollars(), decimals=0, prefix="$"))

    if L.sensitivities:
        parts.append("<h2>Sensitivity: the unpriced weights, made explicit</h2>")
        for blk in L.sensitivities:
            rows = "".join(
                "<tr><td>%s</td><td class='num'>%s %s</td></tr>"
                % (_esc(r.label), _esc(format(r.value, ",.0f")), _esc(r.unit))
                for r in blk.rows)
            note = ('<div class="note">%s</div>' % _esc(blk.notes)) if blk.notes else ""
            flip = ('<div class="note"><strong>Flip point:</strong> %s</div>'
                    % _esc(blk.flip)) if blk.flip else ""
            parts.append('<div class="card"><strong>%s</strong> '
                         '<span class="small">varies %s</span>%s'
                         "<table>%s</table>%s</div>"
                         % (_esc(blk.title), _esc(blk.driver), note, rows, flip))

    parts.append("<h2>Caveats</h2>")
    parts.append('<div class="card"><ul>%s</ul></div>'
                 % "".join("<li>%s</li>" % _esc(c) for c in L.caveats))

    # Inputs appendix: every number, traceable.
    parts.append("<h2>Appendix: every input, with its source</h2>")
    rows = []

    def _input_row(name, q: Quantity):
        val = _fmt_qty(q, decimals=2 if (q.is_priced and abs(q.point) < 100) else 0)
        den = ('<div class="small">%s</div>' % _esc(q.denominator)) if q.denominator else ""
        rec = ('<div class="small">recipe: %s</div>' % _esc(q.recipe)) if q.recipe else ""
        sens = ""
        if q.sensitivity:
            sens = ('<div class="small">sensitivity grid: %s</div>'
                    % _esc(", ".join(str(v) for v in q.sensitivity)))
        rows.append("<tr><td><strong>%s</strong>%s</td><td class='num'>%s"
                    "<div class='small'>%s</div></td><td>%s%s</td>"
                    "<td>%s<div class='small'>%s</div>%s%s</td></tr>"
                    % (_esc(name), den, val, _esc(q.unit), _chip(q.status),
                       ('<div class="small">conf: %s</div>' % _esc(q.confidence))
                       if q.confidence else "",
                       _esc(q.source), "", rec, sens))

    for k, q in cfg.counts.items():
        _input_row("counts." + k, q)
    for grp, block in cfg.weights.items():
        for k, q in block.items():
            _input_row("weights.%s.%s" % (grp, k), q)
    parts.append('<div class="card"><table><tr><th>Input</th><th>Value</th>'
                 "<th>Status</th><th>Source</th></tr>%s</table></div>" % "".join(rows))

    parts.append("<footer>Generated by weighing_machine (alert-north-star, "
                 "suph-projects). Rules of the road: name your NOC denominator; "
                 "counts plus dollars, never dollars alone; unpriced means "
                 "unpriced, not zero. Ranges are worst-case interval "
                 "propagation.</footer>")
    parts.append("</div>")

    return ("<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>Weighing Machine: %s</title><style>%s</style></head><body>"
            "%s</body></html>" % (_esc(L.alert_name), _CSS, "".join(parts)))
