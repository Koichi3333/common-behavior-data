---
name: Portability finding
about: You ran CBD somewhere new and something broke. This is the most valuable issue type here.
title: "[finding] "
labels: compatibility
---

<!-- Pick a behavior. Run it somewhere new. Tell us what breaks.
     See docs/compatibility_findings.md for the register this feeds. -->

## What did you run, and where?

<!-- Source clip / dataset, which generator, which adapter, which target.
     If the target does not run in Colab, say what class of machine you used —
     GPU, memory, runtime version. No project, host or account names, please. -->

## What worked

## What broke

<!-- Be specific. "The reach ends in the wrong place" is a start;
     "the hand ends 0.29 m from where the image puts it" is a finding. -->

## What did you correct, and how much did it change?

<!-- Numbers if you have them: residual, penetration, RMSE, frames affected. -->

## Which kind of problem is it?

- [ ] **Source** — the capture itself was bad
- [ ] **Generator** — the channel exists in the spec but is written wrong or empty
- [ ] **Specification** — canonical CBD carries no such channel at all
- [ ] **Target constraint** — this target simply cannot do it
- [ ] Not sure

## What is still unresolved?
