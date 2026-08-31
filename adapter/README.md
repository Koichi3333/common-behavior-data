# `adapter/` — CBD to a target system

[← back to README](../README.md) ·
[Specification](../specification/README.md) ·
[Architecture](../docs/architecture.md)

**Status: placeholder.** This directory is where adapters will live. Today an
"adapter" is still a section of a demo notebook in [`examples/`](../examples/);
extracting those into reusable code here is the point of this directory.

## What belongs here

Anything that **reads** Common Behavior Data and converts it for a specific
engine, embodiment, or format. One subdirectory per target:

| Target | Today | Where it runs today |
|---|---|---|
| MuJoCo (`humanoid.xml` + `motion.npz`) | Available | Demo A / Demo B notebooks |
| Unity / VRM (`motion.vrma`) | Available | Demo A notebook |
| MediaPipe overlay video | Available | Demo A notebook |
| Dataset views (`frames.jsonl` + CSVs) | Available | Demo A notebook |
| Robot embodiments (e.g. SO-101) | Planned | — |
| LeRobot · Isaac · ROS 2 · Blender / Unreal | Planned | — |

## Rules for an adapter

From [`CONTRIBUTING.md`](../CONTRIBUTING.md), unchanged:

1. **Read canonical data**, not another adapter's output
2. **Convert coordinates at your boundary** — canonical is Y-up, right-handed,
   person facing +Z
3. **Keep model and motion separate** where the target format allows it
4. **Do not promote candidates** — `grasp_candidate` must not become `grasp`
5. **Report what you could not represent**, rather than silently approximating
6. **Preserve provenance** — if you derive a position, say how

If a rule blocks you, that is interesting: it probably means the schema is
missing something. Open an issue.

## Open design question

The adapter *contract* is not formalised yet — what a consumer is guaranteed to
find, how it declares which parts it uses, and how it reports what it dropped.
See [Architecture → what the adapter interface has to become](../docs/architecture.md)
and [Specification → open questions](../specification/README.md#open-questions).
Adapters drive the specification here, not the other way around.
