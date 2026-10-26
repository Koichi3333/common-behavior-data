# `docs/` — Explain the architecture and philosophy

[← back to README](../README.md) · [Specification](../specification/README.md) ·
[Showcase](../showcase/)

**What is this?** The reasoning behind the repository, kept out of the code. Why
the project is shaped this way, how the pieces fit, what has already broken, and
what is honestly not true yet.

| | |
|---|---|
| **Input** | decisions, results and failures from real runs |
| **Output** | prose — no code, no data |
| **Purpose** | Let someone judge the design without reading four adapters first |
| **Related** | [`specification/`](../specification/README.md) defines the *data* · this defines the *thinking* |

## Start with one of these

| If you want to know… | Read |
|---|---|
| **What the idea is**, in plain terms | [`concept.md`](concept.md) |
| **Why an observation is treated as an asset** — and why this is not a video-only project | [`behavior_asset.md`](behavior_asset.md) |
| **How the pieces fit together** | [`architecture.md`](architecture.md) |
| **Where each step runs**, and the rule for new targets | [`runtime_environments.md`](runtime_environments.md) |
| **The gap on each body** — what broke, with numbers | [`compatibility_findings.md`](compatibility_findings.md) — the gap register |
| **What is not true yet** | [`limitations.md`](limitations.md) |
| **What comes next** | [`roadmap.md`](roadmap.md) |
| **Why this is open** rather than a product | [`ecosystem.md`](ecosystem.md) |

`media/` holds the images and the technical concept deck used by the READMEs.

## The two pages that carry the most weight

**[`compatibility_findings.md`](compatibility_findings.md)** — the gap
register — is the one that makes the project cumulative. Adapters are deliberately
[self-contained](../adapters/README.md#self-contained-beats-dry), so code does
not travel between them — findings do. Every entry says which of four things it
is (source issue, generator issue, specification gap, target constraint),
because the four have completely different consequences and only the first three
flow upstream.

**[`limitations.md`](limitations.md)** exists for the opposite reason. A reader
who discovers a limitation themselves stops believing the rest of the page.

## What belongs here

Design reasoning, architecture, philosophy, and the record of what was learned.

What does **not** belong here:

- **The data format** — that is [`specification/`](../specification/README.md)
- **How to run something** — that goes in the README of the directory that runs it
- **How to contribute** — that is [`CONTRIBUTING.md`](../CONTRIBUTING.md)
- **Results and videos** — those are [`showcase/`](../showcase/)

## A note on tone

These pages are written to be falsifiable. Where something works, it is stated
with the number that shows it; where it does not, that is stated too, in the
same voice. A document here that only reports successes is not finished.
