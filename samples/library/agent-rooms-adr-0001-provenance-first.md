---
title: 'Agent Rooms decision 0001: build promote-with-provenance first'
source_type: note
status: published
topics: [Agent Rooms, Decisions]
tags: [ADR, provenance]
entities: [Agent Rooms]
---
# 0001: Build promote-with-provenance before any UI

Status: superseded in part by ADR 0002 (the provenance-first principle stands; the standalone-platform implementation does not).

Context: existing group AI products are either shared-by-default, where every member's agent output lands in the same visible stream with no boundary to cross, or single-player, where an agent's output never leaves one person's session. None of them have a private-to-shared boundary that a member deliberately crosses. That boundary, and the audit trail it produces, is the moat for this product, and it is much harder to add correctly after a UI and a set of ad hoc data shapes already exist.

Decision: build the promote-with-provenance data model, described in docs/design/promote-provenance.md, before any UI work begins. The v0 scope is BYOK-only agent sessions, an open-net sandbox for builders, and creator-adjudicated adoption, with no voting or rotating adjudication yet.

Consequences: this slows down the first demo, since there is no chat surface or sidebar to show yet. In exchange, the product is auditable from day one, because every canonical build byte already traces to a Proposal, a Fork chain, and an Adoption by construction rather than by later retrofit. The schema also carries fields for pluggable governance (Room.adoptionPolicy) and for future hosted-inference support (AgentSession.byok) so that neither voting-based adjudication nor a hosted-inference option requires a schema migration when they are added.

Date: 2026-07-22
