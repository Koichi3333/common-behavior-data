---
name: Gap report (portability finding)
about: You ran CBD on a new body and something did not carry over. This is the most valuable issue type here.
title: "[gap] "
labels: compatibility
---

<!-- Pick a behavior. Run it on a new body. Tell us where the gap is.
     See docs/compatibility_findings.md — the gap register this feeds. -->

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

## Which kind of gap is it?

- [ ] **Data gap** — the record does not carry it (closable upstream)
- [ ] **Body gap** — the two bodies genuinely disagree (not closable; publish the number)
- [ ] Not sure

## Who owns it?

- [ ] **Source** — the capture itself was bad
- [ ] **Generator** — the channel exists in the spec but is written wrong or empty
- [ ] **Specification** — canonical CBD carries no such channel at all
- [ ] **Target constraint** — this target simply cannot do it
- [ ] Not sure

## What is still unresolved?
