# Contributing

[← back to README](README.md)

Thanks for looking. This is an early, independent open-source experiment, and
contribution friction is deliberately low.

## Philosophy

Three things shape how this project takes changes:

1. **Adapters drive the specification, not the other way around.** The schema
   should change because a real integration proved it should — not because a
   design felt tidier in the abstract.
2. **Honesty over polish.** A documented limitation is worth more than a
   flattering demo. If you find a claim the code does not support, that is a bug.
3. **The core stays small.** The behavior representation, its semantics, and the
   adapter contract are maintained centrally. Everything at the edges is better
   built by the people who actually use those systems.

## What is especially welcome

- **Adapters** — robot embodiments, simulators, engines, content pipelines
- **Schema feedback** — especially "I tried to load CBD into X and here is what
  was missing"
- **Reference demos** — a small, honest, end-to-end example beats a large
  speculative one
- **Tools** — visualisation, inspection, validation, conversion, evaluation
- **Documentation** — clarity fixes, corrections, translations
- **Bug reports** — including "the notebook broke in Colab as of today"
- **Research feedback** — pointers to prior art we should be building on or
  citing

## What to open first

| You want to | Do this |
|---|---|
| Fix a typo, a broken link, a wrong claim | Open a PR directly |
| Report a bug | Open an [issue](https://github.com/Koichi3333/common-behavior-data/issues) |
| Propose an adapter | Open an [issue](https://github.com/Koichi3333/common-behavior-data/issues) using the adapter proposal template |
| Change the schema, or anything structural | Open a [Discussion](https://github.com/Koichi3333/common-behavior-data/discussions) **first** |
| Ask whether something is in scope | Open a Discussion — asking is free |

For anything that changes the representation, please discuss before writing
code. Not for process reasons: the schema is unstable, and coordinating early
saves you from building against a version that is about to move.

## Suggested discussion categories

**Show & Tell** · **Adapter Requests** · **Integration Ideas** · **Research** ·
**Industry Use Cases** · **Partnerships**

## Issue labels

Four are applied automatically by the
[issue templates](.github/ISSUE_TEMPLATE/): `bug`, `adapter`, `schema`,
`compatibility`.

The fuller set below matches the shape of this repository, so an issue can be
found by the part of the project it belongs to. Labels are a repository setting
rather than a file, so if one you need does not exist yet, say so in the issue
and it will be created.

| Label | For |
|---|---|
| `good first issue` | Small, self-contained, no repository history required to start |
| `adapter` | A new target, or an existing one behaving wrongly |
| `generator` | Anything that writes CBD from a source |
| `tool` | Standalone utilities — video prep, masking, comparison, inspection |
| `experiment` | Exploratory work using existing generators and adapters |
| `showcase` | Results, videos, comparisons |
| `specification` / `schema` | The canonical representation itself |
| `compatibility` | **Portability findings** — where behavior broke on a target |
| `physics` | Contact, collision, settling, dynamic feasibility |
| `embodiment` | Body structure, joint limits, retargeting, proportions |
| `video asset` | Source clips and behavior cases the pipeline handles badly |
| `ML experiment` | Training, generation, evaluation on CBD datasets |
| `screen behavior` | Non-body observation — screen recordings, UI workflows |
| `documentation` | READMEs, docs, anything a first-time reader stumbles on |

`compatibility` is the one most worth using. A portability finding — *this
behavior broke on this target, by this much* — is the contribution this project
compounds on, and it has [its own template](.github/ISSUE_TEMPLATE/portability_finding.md)
and [its own register](docs/compatibility_findings.md).

## Where code goes

Every directory has one role, and one README that states it:

| Directory | Role | What goes there |
|---|---|---|
| [`generators/`](generators/) | **Create CBD** | Anything that **writes** CBD — video → CBD, language → CBD, captioning and annotation passes |
| [`adapters/`](adapters/) | **Use CBD somewhere** | Anything that **reads** CBD and converts it for an engine, embodiment or format |
| [`tools/`](tools/) | **Prepare and manipulate assets** | Independent utilities — video prep, masking, asset creation, comparison, dataset inspection |
| [`experiments/`](experiments/) | **Try something with CBD** | Research code that uses existing generators and adapters — learning prototypes, re-embodiment, evaluation |
| [`examples/`](examples/) | **Initial Minimum Experience** | The original end-to-end notebooks, preserved as they are |
| [`showcase/`](showcase/) | **See what CBD can do** | Results, with what worked and what broke. Links, not copies |

Rules of thumb:

- If it targets one specific engine or body, it is an **adapter**, not a tool.
- **Do not factor shared logic out of adapters into `tools/`.** Adapters stay
  self-contained on purpose — physics assumptions and body structures differ too
  much for a shared helper to be right for all of them. Share the *finding*
  instead: [`docs/compatibility_findings.md`](docs/compatibility_findings.md).
- An experiment that stabilises **graduates** into `generators/`, `adapters/` or
  `tools/`, after repeated success and a clear interface. Nothing in
  `experiments/` is part of the stable surface, and nothing stable may import
  from it.
- **Do not create empty directories** for future work. Put the idea in the
  roadmap; add the directory when there is code.

`generators/` and `adapters/` hold working code. `tools/` and `experiments/` are
still mostly signposts — the learning code lives inside the `examples/`
notebooks, and extracting a piece of it into the right directory is a genuinely
useful contribution. Open an issue first so two people do not extract the same
thing.

## Working on the notebooks

The two notebooks in `examples/` are the technical source of truth for what CBD
currently is. A few conventions:

- **All comments, docstrings and log output are English.** No exceptions — this
  repository is read internationally.
- **Comments should explain *why*.** The interesting content in these notebooks
  is the reasoning: why interactions are candidates, why the object proxy holds
  its last known position, why the lower body is frozen. Preserve that when you
  edit.
- **Never commit credentials.** Keys are read from Colab Secrets or the
  environment only. There are no key values anywhere in this repository, and
  there should never be.
- **Clear outputs before committing.** Notebook outputs are environment-specific
  noise and bloat the repository. `jupyter nbconvert --clear-output --inplace
  path/to/notebook.ipynb` is enough.
- **Preserve Colab usability.** These are meant to run top-to-bottom in a fresh
  Colab runtime with no local setup.
- **Keep cell numbering stable** (`[1]`, `[3.5]`, `[5.5]` …). The documentation
  references cells by number.

## Writing an adapter

New adapters belong in [`adapters/`](adapters/), **one subdirectory per target,
self-contained**. Until the adapter contract is formalised (see
[open questions](specification/README.md#open-questions)), the working rules are:

1. **Read canonical data**, not another adapter's output
2. **Convert coordinates at your boundary** — the canonical frame is Y-up,
   right-handed, person facing +Z
3. **Keep model and motion separate** where the target format allows it
4. **Do not promote candidates** — a field named `grasp_candidate` must not
   become `grasp` downstream
5. **Report what you could not represent**, rather than silently approximating it
6. **Preserve provenance** — if you derive a position, say how

7. **Stay self-contained.** Keep your retarget, contact, physics, placement and
   validation machinery inside your own directory, even if another adapter has
   something that looks similar. Portability and readability of one adapter beat
   code DRY across all of them.
8. **State where you run.** If your target cannot run in Colab, say so at the
   top of your README, name the class of machine you used (GPU, memory, runtime
   version) — never a project, host or account — and commit your outputs so the
   result is readable without that machine. See
   [`docs/runtime_environments.md`](docs/runtime_environments.md).

And when you are done, write down what you learned, not just what you built:

```text
What worked · What broke · What was corrected · Why · How much it changed · What is unresolved
```

Classify each finding as a **source**, **generator**, **specification** or
**target** issue — they have different owners — and add it to
[`docs/compatibility_findings.md`](docs/compatibility_findings.md). A finding
with a number attached is worth several without one.

If a rule blocks you, that is interesting. Say so in an issue: it probably means
the schema is missing something.

## Style

- Prefer concrete language over marketing language
- Prefer "experimental", "prototype", "currently supports", "planned"
- Avoid "revolutionary", "industry standard", "production-ready", "universal"
- Short paragraphs, real examples, diagrams where they help

## Licensing

Contributions are accepted under the [Apache License 2.0](LICENSE), matching the
repository's own license (inbound = outbound). There is no separate CLA.

If you contribute data, media, or a third-party asset, say clearly what its
license is — see [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Assets
without clear redistribution rights cannot be merged.

## Code of conduct

Be decent. Assume good faith, critique ideas rather than people, and remember
that a lot of the people reading this are working outside their primary field.
Behaviour that makes the project worse to participate in is not welcome, and
maintainers will act on it.

---

**Not sure where to start?** Take an episode from
[`examples/human-capture/sample_output/`](examples/human-capture/sample_output/),
try to load it into a system this project has never heard of, and tell us what
was missing. That report is the single most useful thing you can send.
