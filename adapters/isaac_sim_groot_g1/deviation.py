#!/usr/bin/env python3
"""How far the delivered result is from what was asked for.

`provenance.py` answers *where did this value come from*. It does not answer
*how wrong is it*, and for a pipeline whose whole licence is "correct the
capture, declare the correction" that second question is the one that keeps the
licence honest. A tier of `derived` on a seat height says nothing about whether
the pelvis ended up on the seat.

So every stage that moves a number away from what something asked for records
the move here, as **asked / got / error**, in the quantity's own units, against
a tolerance where one exists. Two properties follow, and both matter more than
the prose in any report:

* nothing is a note. "The retarget reproduces it rather than correcting it" is
  a sentence; `midline r_knee: asked <= 0.041 m, got 0.110 m, error +0.069 m,
  FAIL` is a number that a later run can be compared against.
* a deviation with no tolerance is still recorded. Scene scale has no pass or
  fail -- 0.784 is a decision, not an error -- but a consumer measuring
  furniture needs to find it, so it is in the same ledger, marked `informational`.

Stages report into one ledger so the failures sort together regardless of which
part of the pipeline produced them.
"""
from __future__ import annotations

import json
from collections import OrderedDict

STAGES = ("cleanup", "scene", "retarget", "physics", "contact")


class Deviations:
    """asked / got / error, per quantity, across every stage."""

    def __init__(self):
        self.entries = []

    def record(self, quantity: str, stage: str, asked, got, unit: str,
               tolerance=None, how: str = "", direction: str = "abs",
               note=None):
        """Log one deviation.

        asked      what the stage was aiming at (a value, or a bound)
        got        what came out
        tolerance  None -> informational; a number -> pass/fail on |error|
        direction  "abs"  error is |got - asked|
                   "over" error is max(0, got - asked)   (a ceiling: <= asked)
                   "under" error is max(0, asked - got)  (a floor:   >= asked)
        """
        a, g = (float(asked) if asked is not None else None), float(got)
        if a is None:
            err = None
        elif direction == "over":
            err = max(0.0, g - a)
        elif direction == "under":
            err = max(0.0, a - g)
        else:
            err = abs(g - a)
        ok = None if (tolerance is None or err is None) else bool(err <= float(tolerance))
        self.entries.append(OrderedDict(
            quantity=quantity, stage=stage, asked=a, got=g, error=err,
            unit=unit, tolerance=(float(tolerance) if tolerance is not None else None),
            status=("informational" if ok is None else ("ok" if ok else "FAIL")),
            how=how, **({"note": note} if note else {})))
        return self.entries[-1]

    def informational(self, quantity, stage, got, unit, how=""):
        return self.record(quantity, stage, None, got, unit, None, how)

    # -- reading -----------------------------------------------------------
    def failures(self):
        return [e for e in self.entries if e["status"] == "FAIL"]

    def worst(self, n=5, stage=None):
        pool = [e for e in self.entries
                if e["error"] is not None and e["tolerance"] is not None
                and (stage is None or e["stage"] == stage)]
        return sorted(pool, key=lambda e: -(e["error"] / (e["tolerance"] or 1e-9)))[:n]

    def by_stage(self):
        out = {}
        for e in self.entries:
            out.setdefault(e["stage"], []).append(e)
        return out

    def passed(self) -> bool:
        return not self.failures()

    def report(self):
        return {
            "definition": {
                "asked": "what the stage aimed at",
                "got": "what came out",
                "error": "abs |got-asked|, or the one-sided overshoot for a bound",
                "status": "ok / FAIL against tolerance; informational when there is none",
            },
            "passed": self.passed(),
            "counts": {"total": len(self.entries),
                       "checked": sum(1 for e in self.entries if e["tolerance"] is not None),
                       "failed": len(self.failures())},
            "failures": self.failures(),
            "by_stage": self.by_stage(),
        }

    def summary_line(self) -> str:
        c = self.report()["counts"]
        return (f"{c['checked']} checked, {c['failed']} failed, "
                f"{c['total'] - c['checked']} informational "
                f"[{'PASS' if self.passed() else 'FAIL'}]")

    def table(self, entries=None, width=34):
        """Fixed-width lines, for the console report."""
        rows = []
        for e in (entries if entries is not None else self.entries):
            asked = "--" if e["asked"] is None else f"{e['asked']:.4g}"
            err = "--" if e["error"] is None else f"{e['error']:+.4g}"
            tol = "" if e["tolerance"] is None else f" / {e['tolerance']:.4g}"
            mark = {"ok": "ok  ", "FAIL": "FAIL", "informational": "--  "}[e["status"]]
            rows.append(f"[{mark}] {e['quantity']:<{width}} "
                        f"asked {asked:>9}  got {e['got']:>9.4g}  "
                        f"err {err:>9}{tol} {e['unit']}")
        return rows

    def __str__(self):
        return json.dumps(self.report(), indent=2)
