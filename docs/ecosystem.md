# Ecosystem

[← back to README](../README.md)

## The bet

Large organisations have structural advantages in nearly everything that
matters for robotics and Physical AI: proprietary datasets, foundation model
scale, dedicated hardware, vertically integrated robot stacks, cloud
infrastructure, and large product teams.

Competing on any of those from a personal GitHub account would be silly.

The hypothesis this project tests instead is that value can accumulate in the
properties those advantages do *not* produce:

- **Neutrality** — a layer that belongs to no vendor is usable by all of them
- **Interoperability** — the value grows with the number of connected systems
- **Open specifications** — a schema anyone can read, criticise and implement
- **Reusable behavior semantics** — meaning, not just numbers
- **Adapter-based integration** — new systems join without central coordination

## The intended shape

```text
Common Behavior Data
        ↓
Open specification / OSS
        ↓
Adapters + reference demos
        ↓
Users / contributors
        ↓
Supporting companies / partners
        ↓
Cross-company ecosystem
        ↓
De facto interoperability layer
```

```text
Core maintains the behavior representation
        ↓
Contributors add adapters and tools
        ↓
More systems become compatible
        ↓
More users
        ↓
More contributors and partners
```

**This is a design goal, not a description of reality.** There is no ecosystem
yet. There are two demos, one representation, and an open question. This page
describes where the project is aimed so that people deciding whether to
contribute know what they would be contributing to.

## Division of labour

The core project intends to focus on the parts that only work if one group keeps
them coherent:

- the canonical CBD representation and its semantics
- provenance and lineage
- language / motion / object alignment
- the adapter interface
- compatibility and validation
- roadmap and governance

Everything at the edges is better built by the people who actually use those
systems:

- robot adapters (SO-101, LeRobot, arbitrary embodiments)
- simulator adapters (Isaac, others)
- ROS 2 integration
- Blender / Unreal / other content pipeline exporters
- IK and retargeting
- visualisation and inspection tools
- evaluation tooling
- VLM / vision integrations
- reference applications in specific domains

If you maintain one of those systems, you know its conventions far better than
this project ever will. That asymmetry is the point of an adapter architecture.

## Who this is for

Primary audience — technically curious people working in:

robotics and Physical AI · robot learning and VLA · simulation · computer vision
and human motion · multimodal learning · game / avatar / VRM tooling · research ·
open interoperability

Secondary, where behavior data is the raw material:

manufacturing and logistics · motion analytics · sports and skill analysis ·
vertical SaaS · companies exploring integration or partnership

## Getting involved

There is no membership, no CLA beyond Apache-2.0 inbound=outbound, and no
process to speak of yet. Useful ways in, roughly in order of usefulness:

1. **Try to break the schema.** Take an episode from
   [`examples/human-capture/sample_output/`](../examples/human-capture/sample_output/)
   and try to load it into a system this project has never heard of. What is
   missing? That report is worth more than a patch.
2. **Write an adapter** for something you already use.
3. **Argue with a design decision** in an issue or discussion — especially about
   the parts marked open in [`specification/`](../specification/README.md).
4. **Tell us what you are building.** Even "I looked at this for a robot arm and
   here is why it does not fit" is a genuinely useful contribution.

Suggested discussion categories: **Show & Tell**, **Adapter Requests**,
**Integration Ideas**, **Research**, **Industry Use Cases**, **Partnerships**.

---

**See also:** [Contributing](../CONTRIBUTING.md) · [Roadmap](roadmap.md) · [Concept](concept.md)
