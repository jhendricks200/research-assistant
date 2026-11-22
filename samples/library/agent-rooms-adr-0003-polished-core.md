---
title: 'Agent Rooms decision 0003: polished core, narrow breadth'
source_type: note
status: published
topics: [Agent Rooms, Decisions]
tags: [ADR, scope]
entities: [Agent Rooms]
---
# 0003: Polished core, narrow breadth

Context: ADR 0002 chose a bare Discord bot plus CLI on the assumption that testers would be developer pods already living in Discord with their own agent CLIs. The founder's actual recruiting pool is vibe-coders and curious builders from communities like Lovable's, without CLI habits, and a bare bot risks a false negative where testers judge plumbing rather than the product. The interface is part of the comprehension-cost hypothesis, not cosmetic.

Decision: v0 becomes a polished single-room web product with narrow breadth. It comprises a polished proposal feed, a hosted private agent sidebar as the primary agent surface for testers, running a cheap capable open-weight model in the DeepSeek V4-Flash class so per-tester inference is near zero, a beautiful proposal page showing intent, remix note, preview, diff, author, and lineage, a satisfying promote interaction, a safe one-click fork flow, and a clear adoption state.

Narrowness is kept from the reviews: one repository type, one web-app template, one room owner, one adoption method, manual operational intervention, and no billing, discovery, boosts, reputation algorithm, moderation system, or generalized platform. Explicitly retained from ADR 0002 are GitHub as the only canonical build with SHA-pinned PR-merge adoption, the owned surfaces, the schema commitments, the Stage 0 agent smoke test, and the eligible-exposure validation gates. Discord is reduced to notifications and unfurls, with the experience living on the web.

Additional decision: before any tester is recruited, a seeded demonstration room is built in which fictional contributors have already promoted, forked, remixed, and adopted, so the first real user opens a room that communicates the entire idea visually.

Consequences: a hard three-week build box replaces the one-week bot estimate. The CLI and MCP surface move from a v0 requirement to a fast-follow for power users. The web surface removes the CLI-install confound from Jam B entirely. The risk accepted is spending two extra weeks before first human contact.

Date: 2026-07-23
