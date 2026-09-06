#!/usr/bin/env python3
"""Where every quantity in the adapter's output came from.

Adapter rule 6 is *preserve provenance -- if you derive a position, say how*,
and rule 5 is *report what you could not represent, rather than silently
approximating*. v1 answered both by refusing: what canonical CBD did not carry
was left out and listed in `not_represented`.

That is safe for the record and wrong for the target. A G1 whose chest and
shoulders stay at zero because the dataset has no rotation for them is not a
faithful record of anything -- it is a broken robot. So this ledger takes the
other half of rule 5 seriously instead: approximate, but never *silently*.

Every quantity carries a tier:

    measured     canonical CBD has it
    derived      geometry from canonical CBD
    prior        a class-level constant (the object catalog, anthropometry)
    synthesized  the adapter authored it, to keep the target self-consistent
    unavailable  nothing filled it

`unavailable` is a bug in normal operation, not an outcome: every quantity the
target needs has a path down to `synthesized`. What the ledger is for is the
question that replaces "what did you drop?" -- **how much of this is still
CBD?** `evidence_ratio()` answers it, and `check_floor()` fails the run when
the answer gets too low to claim the motion came from the dataset.

A quantity that is *always* synthesized is not an adapter defect. It is a
missing channel in the schema, which is what the repository's own README asks
adapters to surface: "If a rule blocks you, that is interesting."
`spec_feedback()` collects those.
"""
from __future__ import annotations

import json
from collections import OrderedDict

TIERS = ("measured", "derived", "prior", "synthesized", "unavailable")
EVIDENCE_TIERS = ("measured", "derived")   # still traceable to the dataset
DEFAULT_FLOOR = 0.70


class Provenance:
    """A weighted ledger of tier decisions, one entry per quantity."""

    def __init__(self, floor: float = DEFAULT_FLOOR):
        self.floor = float(floor)
        self.entries = OrderedDict()

    # -- recording ---------------------------------------------------------
    def record(self, quantity: str, tier: str, rule: str, weight: float = 1.0,
               detail=None, spec_gap: str | None = None):
        """Note how one quantity was filled.

        quantity  dotted name, e.g. "joint.left_shoulder_pitch" or "object.cup"
        tier      one of TIERS
        rule      short human-readable reason, kept in the report verbatim
        weight    how much of the output this covers -- channels x frames, so
                  one joint over 96 frames outweighs one object's mass
        spec_gap  set when the fill exists only because canonical CBD has no
                  channel for it; collected by spec_feedback()
        """
        if tier not in TIERS:
            raise ValueError(f"unknown tier {tier!r}")
        self.entries[quantity] = {
            "tier": tier, "rule": rule, "weight": float(weight),
            "detail": detail, "spec_gap": spec_gap,
        }
        return tier

    def measured(self, q, rule, weight=1.0, detail=None):
        return self.record(q, "measured", rule, weight, detail)

    def derived(self, q, rule, weight=1.0, detail=None):
        return self.record(q, "derived", rule, weight, detail)

    def prior(self, q, rule, weight=1.0, detail=None):
        return self.record(q, "prior", rule, weight, detail)

    def synthesized(self, q, rule, weight=1.0, detail=None, spec_gap=None):
        return self.record(q, "synthesized", rule, weight, detail, spec_gap)

    def unavailable(self, q, rule, weight=1.0, detail=None):
        return self.record(q, "unavailable", rule, weight, detail)

    # -- reading -----------------------------------------------------------
    def weights(self):
        totals = {t: 0.0 for t in TIERS}
        for e in self.entries.values():
            totals[e["tier"]] += e["weight"]
        return totals

    def ratios(self):
        totals = self.weights()
        total = sum(totals.values()) or 1.0
        return {t: totals[t] / total for t in TIERS}

    def evidence_ratio(self) -> float:
        """Fraction of the output still traceable to canonical CBD."""
        r = self.ratios()
        return sum(r[t] for t in EVIDENCE_TIERS)

    def check_floor(self):
        """(passed, message). Below the floor the run is not evidence any more."""
        got = self.evidence_ratio()
        ok = got >= self.floor
        return ok, (f"measured+derived {got:.1%} "
                    f"{'>=' if ok else '<'} floor {self.floor:.0%}")

    def unavailable_quantities(self):
        return [q for q, e in self.entries.items() if e["tier"] == "unavailable"]

    def spec_feedback(self):
        """Fills that exist only because the schema has no channel for them."""
        out = {}
        for q, e in self.entries.items():
            if e["spec_gap"]:
                out.setdefault(e["spec_gap"], []).append(q)
        return out

    # -- output ------------------------------------------------------------
    def report(self):
        ok, msg = self.check_floor()
        by_tier = {t: [] for t in TIERS}
        for q, e in self.entries.items():
            by_tier[e["tier"]].append(
                {"quantity": q, "rule": e["rule"], "weight": e["weight"],
                 **({"detail": e["detail"]} if e["detail"] is not None else {})})
        return {
            "tiers": {
                "definition": {
                    "measured": "canonical CBD carries it",
                    "derived": "geometry from canonical CBD",
                    "prior": "class-level constant (catalog / anthropometry)",
                    "synthesized": "authored by the adapter to keep the target consistent",
                    "unavailable": "nothing filled it -- a defect, not an outcome",
                },
                "weight_is": "channels x frames covered",
                "ratio": {t: round(v, 4) for t, v in self.ratios().items()},
            },
            "evidence": {
                "measured_plus_derived": round(self.evidence_ratio(), 4),
                "floor": self.floor, "passed": ok, "note": msg,
            },
            "unavailable": self.unavailable_quantities(),
            "spec_feedback": self.spec_feedback(),
            "by_tier": by_tier,
        }

    def summary_line(self) -> str:
        r = self.ratios()
        parts = " / ".join(f"{t} {r[t]:.0%}" for t in TIERS if r[t] > 0.0005)
        ok, msg = self.check_floor()
        return f"{parts}   [{'PASS' if ok else 'FAIL'}: {msg}]"

    def __str__(self):
        return json.dumps(self.report(), indent=2)
