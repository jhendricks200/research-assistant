---
title: 'Agent Rooms decision 0002: attach to Discord and GitHub'
source_type: note
status: published
topics: [Agent Rooms, Decisions]
tags: [ADR, integrations]
entities: [Discord, GitHub]
---
# 0002: Attach to Discord and GitHub instead of building a standalone platform

Status: amended by ADR 0003 (the social surface moves from a bare Discord bot to a polished single-room web product; git grounding, owned surfaces, schema, and validation gates stand).

Context: the day-one design (ADR 0001) specified a standalone platform with a custom append-only BuildVersion ledger. Three rounds of adversarial review by external models (Codex and Grok, July 22, 2026) converged on attaching to existing surfaces and grounding provenance in git instead.

Decision: v0 attaches to Discord as the social surface and GitHub as the build surface, where adopt equals a SHA-pinned PR merge. A required CLI is the agent surface, with MCP as an optional mode. The custom version ledger is deleted in favor of git plus app metadata. The fork payload is the five-part bundle with an author-approved remix note. Validation runs as two instrumented jams with graded gates before any platform investment.

Scope of the lock: the v0 experiment shape and the schema commitments are locked. The schema commitments are DAG parents via parentProposalIds, global proposal ids, the owned-surfaces list, and immutable versions with headCommit. Platform strategy, moat strategy, and monetization remain provisional until the jams produce evidence.

Consequences: this is faster to test and honest about the riskiest assumption, at the cost of training users on surfaces we do not own. The mitigations are the owned-surfaces list in docs/design/promote-provenance.md and shipping public credit profiles by v0.1.

Date: 2026-07-22
