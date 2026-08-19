"""CLI: weigh one alert config, print the ledger, optionally write HTML.

    python3 -m weighing_machine configs/dwelling_age.json -o report.html
    python3 -m weighing_machine configs/dwelling_age.json --scale 0.93
    python3 -m weighing_machine configs/dwelling_age.json --tolerance-bar 100
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import load
from .model import weigh
from .report import render_html


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python3 -m weighing_machine",
        description="Weigh an underwriting alert: binds gained vs NOCs, NOEs, "
                    "lost premium. Counts plus dollars, never dollars alone.")
    p.add_argument("config", help="alert config JSON (see configs/)")
    p.add_argument("-o", "--out", help="write a self-contained HTML report here")
    p.add_argument("--scale", type=float, default=1.0,
                   help="linear volume scale, e.g. 0.93 for the top-7-states "
                        "cut or 0.5 for a 50%% holdout (default 1.0)")
    p.add_argument("--tolerance-bar", type=float, default=None,
                   help="accepted binds-per-NOC exchange rate (LaNae's number, "
                        "once asked). Shown against the computed rate.")
    p.add_argument("--json", action="store_true", dest="as_json",
                   help="also dump the ledger lines as JSON to stdout")
    args = p.parse_args(argv)

    cfg = load(args.config)
    ledger = weigh(cfg, scale=args.scale, tolerance_bar=args.tolerance_bar)

    print(ledger.to_text())

    if args.as_json:
        payload = {
            "alert_id": ledger.alert_id, "direction": ledger.direction,
            "scale": ledger.scale,
            "lines": {
                ln.key: {
                    "label": ln.label, "kind": ln.kind, "status": ln.status,
                    "point": ln.quantity.point,
                    "low": ln.quantity.lo if ln.quantity.is_priced else None,
                    "high": ln.quantity.hi if ln.quantity.is_priced else None,
                } for ln in ledger.lines},
        }
        print(json.dumps(payload, indent=2))

    if args.out:
        html_text = render_html(ledger, cfg)
        with open(args.out, "w") as f:
            f.write(html_text)
        print("\nHTML report written to %s (%d bytes)"
              % (args.out, len(html_text)), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
