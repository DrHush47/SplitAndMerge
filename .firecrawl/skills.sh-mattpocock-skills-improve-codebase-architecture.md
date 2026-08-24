# improve-codebase-architecture

Installation

CommandPrompt

`$ npx skills add https://github.com/mattpocock/skills --skill improve-codebase-architecture`

Summary

**Analyze codebases for architectural friction and propose module-deepening refactors as testability improvements.**

- Explores codebases organically to surface shallow modules, tightly-coupled components, and untested seams rather than following rigid heuristics
- Applies John Ousterhout's "deep module" principle: small interfaces hiding large implementations for better testability and AI navigability
- Generates multiple radically different interface designs (minimalist, flexible, caller-optimized, ports & adapters) via parallel sub-agents, then recommends the strongest approach
- Creates GitHub issue RFCs documenting the problem space, design trade-offs, and refactoring rationale

SKILL.md

# Improve Codebase Architecture

Surface architectural friction and propose **deepening opportunities** — refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability.

This command is _informed_ by the project's domain model and built on a shared design vocabulary:

- Run the `/codebase-design` skill for the architecture vocabulary ( **module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, **locality**) and its principles (the deletion test, "the interface is the test surface", "one adapter = hypothetical seam, two = real"). Use these terms exactly in every suggestion — don't drift into "component," "service," "API," or "boundary."
- The domain language in `CONTEXT.md` gives names to good seams; ADRs in `docs/adr/` record decisions this command should not re-litigate.

## Process

### 1\. Explore

Read the project's domain glossary (`CONTEXT.md`) and any ADRs in the area you're touching first.

Then use the Agent tool with `subagent_type=Explore` to walk the codebase. Don't follow rigid heuristics — explore organically and note where you experience friction:

Show more

Installs

499.2K

Repository

[mattpocock/skills](https://github.com/mattpocock/skills "mattpocock/skills")

GitHub Stars

178.0K

First Seen

Mar 13, 2026

Security Audits

[Gen Agent Trust HubPass](https://www.skills.sh/mattpocock/skills/improve-codebase-architecture/security/agent-trust-hub) [SocketPass](https://www.skills.sh/mattpocock/skills/improve-codebase-architecture/security/socket) [SnykPass](https://www.skills.sh/mattpocock/skills/improve-codebase-architecture/security/snyk)

improve-codebase-architecture — mattpocock/skills