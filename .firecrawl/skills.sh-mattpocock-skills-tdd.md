# tdd

Installation

CommandPrompt

`$ npx skills add https://github.com/mattpocock/skills --skill tdd`

Summary

**Test-driven development with vertical slices, behavior-focused tests, and incremental red-green-refactor cycles.**

- Emphasizes integration-style tests that verify behavior through public APIs, not implementation details; tests should survive refactors unchanged
- Requires vertical slicing (one test → one implementation → repeat) instead of horizontal slicing (all tests first, then all code), preventing brittle, behavior-insensitive test suites
- Includes planning phase to confirm interface changes, prioritize behaviors to test, and design for testability before writing code
- Provides refactoring guidelines covering duplication extraction, module deepening, and SOLID principles, applied only after all tests pass

SKILL.md

# Test-Driven Development

TDD is the red → green loop. This skill is the reference that makes that loop produce tests worth keeping: what a good test is, where tests go, the anti-patterns, and the rules of the loop. Every section applies on every cycle — consult them before and during the loop, not after.

When exploring the codebase, read `CONTEXT.md` (if it exists) so test names and interface vocabulary match the project's domain language, and respect ADRs in the area you're touching.

## What a good test is

Tests verify behavior through public interfaces, not implementation details. Code can change entirely; tests shouldn't. A good test reads like a specification — "user can checkout with valid cart" tells you exactly what capability exists — and survives refactors because it doesn't care about internal structure.

See [tests.md](https://github.com/mattpocock/skills/blob/HEAD/skills/engineering/tdd/tests.md) for examples and [mocking.md](https://github.com/mattpocock/skills/blob/HEAD/skills/engineering/tdd/mocking.md) for mocking guidelines.

## Seams — where tests go

A **seam** is the public boundary you test at: the interface where you observe behavior without reaching inside. Tests live at seams, never against internals.

**Test only at pre-agreed seams.** Before writing any test, write down the seams under test and confirm them with the user. No test is written at an unconfirmed seam. You can't test everything — agreeing the seams up front is how testing effort lands on the critical paths and complex logic instead of every edge case.

Ask: "What's the public interface, and which seams should we test?"

Show more

Installs

478.9K

Repository

[mattpocock/skills](https://github.com/mattpocock/skills "mattpocock/skills")

GitHub Stars

178.0K

First Seen

Feb 10, 2026

Security Audits

[Gen Agent Trust HubPass](https://www.skills.sh/mattpocock/skills/tdd/security/agent-trust-hub) [SocketPass](https://www.skills.sh/mattpocock/skills/tdd/security/socket) [SnykPass](https://www.skills.sh/mattpocock/skills/tdd/security/snyk)

tdd — mattpocock/skills