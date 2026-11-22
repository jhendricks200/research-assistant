---
title: 'Agent Rooms: promote with provenance, v0 design'
source_type: analysis
status: published
topics: [Agent Rooms, Design]
tags: [provenance, design doc]
entities: [Agent Rooms]
---
# Promote with Provenance: v0 Design (locked)

The design goal is unchanged from day one: an audited bridge between private agent work and shared state. What changes is the foundation. v0 is grounded on git and attached to Discord and GitHub rather than implemented as a standalone platform. This document supersedes the day-one version after three adversarial review rounds (Codex and Grok, July 22, 2026).

## What v0 is and is not

v0 is:

1. A polished single-room web product: a proposal feed, a hosted agent sidebar running a cheap capable open-weight model in the DeepSeek V4-Flash class, and proposal pages showing intent, remix note, preview, diff, author, and lineage.
2. A one-click fork flow and a clear adoption state, both surfaced directly in the web product.
3. A linked GitHub repo per room, serving as the only canonical build and version history, with SHA-pinned PR-merge adoption.
4. Vercel deploy previews.
5. Web apps as the only supported artifact class.
6. Discord notifications and unfurls only; the experience lives on the web.
7. A seeded demonstration room, populated before any tester is recruited, in which fictional contributors have already promoted, forked, remixed, and adopted. It is the same artifact as the Stage 0 agent smoke test: Stage 0's agent participants run under named fictional personas, and their best chains are curated into this room, built once.

v0 is not:

1. A multi-room platform.
2. A billing system.
3. A discovery surface.
4. A reputation algorithm.
5. A moderation system.
6. A CLI or MCP release. Both move to fast-follow for power users; the schema remains agent-agnostic, so any MCP-capable agent becomes first-class the moment that ships.

## Entities

Room is the project identity, maintainer roster, and adoption authority. This information is stored by Agent Rooms and is not inferred from Discord or GitHub. Platform identities (Discord, GitHub) attach to a Contributor via linkedIdentities; all authorization checks, including adoption authority, are performed against Contributor ids, never platform ids.

```typescript
interface Room {
  id: string;
  name: string;
  discordChannelRef: string;
  githubRepoRef: string;
  maintainers: string[]; // contributorId[], references Contributor.id
  adoptionAuthority: 'maintainers';
  createdBy: string;
  license: string; // default 'MIT'
}
```

Contributor identity is cross-room and global by design, so lineage composes into one graph instead of fragmenting per room.

```typescript
interface Contributor {
  id: string; // global, cross-room
  displayName: string;
  linkedIdentities: {
    discord: string | null;
    github: string | null;
  };
}
```

Proposal is the promoted unit. Its state machine is authoritative on the Agent Rooms permalink; the Discord card is a mirror, not a second source of truth. Lineage is a DAG rather than a single parent, because real remixes combine more than one source. Whether and how often a proposal has been forked is derived from its Fork records, not tracked as a state, because forking is unbounded and does not exclude any state transition; the card UI displays a fork count alongside the state.

```typescript
interface Proposal {
  id: string; // globally unique, permalinked
  roomId: string;
  authorContributorId: string;
  state: 'open' | 'superseded' | 'adopted' | 'rejected';
  versions: ProposalVersion[];
  parentProposalIds: string[]; // global ids, may cross rooms
  createdAt: string;
}
```

ProposalVersion is immutable once published. Every fork records the exact versionId it consumed, so later disputes about what was forked from what resolve to a fixed record.

```typescript
interface ProposalVersion {
  versionId: string;
  intentSummary: string;
  diffRef: string;
  baseCommit: string;
  headCommit: string; // exact PR head SHA at promotion time
  contentHash: string; // sha256
  remixNote: RemixNote;
  publishedAt: string;
}
```

RemixNote content is limited to four things: decisions that shaped the change, constraints the remixer must preserve, known risks or incomplete work, and failed approaches, and only when repeating them would be costly. An empty note is a normal, first-class option, not a failure state. The promoter's agent generates the note and passes it to the CLI; the CLI never scrapes Cursor, Claude Code, or Codex session storage, both for privacy and for provider neutrality. Note text is never treated as ground truth in reputation, since a curated note can lie by omission.

```typescript
interface RemixNote {
  bullets: string[]; // one to six, each independently removable
  generatedBy: 'agent-draft';
  authorEdited: boolean;
  lengthCapped: true;
}
```

Fork means initializing a new private workspace from the bundle. It never continues the original agent session and never transfers hidden state.

```typescript
interface Fork {
  id: string;
  proposalId: string;
  proposalVersionId: string;
  byContributorId: string;
  createdAt: string;
}
```

Adoption records that a maintainer merged a proposal's PR into the room's canonical build.

```typescript
interface Adoption {
  id: string;
  proposalId: string;
  proposalVersionId: string;
  roomId: string;
  adoptedByContributorId: string; // must be in maintainers
  expectedHeadCommit: string;
  mergeResult: string;
  adoptionReceiptRef: string; // portable receipt
  adoptedAt: string;
}
```

QAExchange lets questions arrive in the Discord thread, but the answer is mirrored onto the proposal page. The reasoning that enabled a remix should be owned durably, not trapped in Discord scrollback.

```typescript
interface QAExchange {
  proposalId: string;
  question: string;
  answer: string;
  askedBy: string;
  answeredBy: string;
}
```

## The fork bundle

The payload injected into a remixer's workspace is exactly five parts: the artifact (diff or files), the base commit, the lineage chain, the intent summary, and the remix note. Nothing else, ever.

Mechanically, `fork` creates a new branch and a new git worktree, never the current dirty workspace. It writes `.agent-rooms/FORK_CONTEXT.md` and appends a one-line pointer to whatever agent instruction file exists (AGENTS.md, CLAUDE.md, .cursor/rules), because daily agents routinely ignore loose markdown. The instruction-file pointer is the mechanism for the fast-follow CLI path; in v0 the hosted sidebar ingests the fork bundle directly, without needing a pointer file. Jam A must verify that the agent actually cites the note before Jam B results are trusted. A dead fork, where the agent never picks up the injected context, is treated as a payload design failure, not user error.

## Adoption integrity

A proposal card is immutable but its PR is mutable, since contributors can push commits after promotion. Adoption supplies expectedHeadCommit to GitHub's merge API and fails if the PR head has moved, so the room can never merge code different from what was promoted, hashed, and credited. Promotion itself must come from a clean task branch or from explicitly selected hunks.

## Safety mechanics (v0, not deferred)

1. Secret scanning runs on every promote, across the diff and the remix note, before publish, with an exact publish preview shown to the promoter.
2. Emergency redaction exists for leaked remix notes: the note content is redacted, the original content hash is preserved, and a visible tombstone marks the redaction. Adopted git history is never rewritten.
3. Remix notes carry a hard length cap with a short default draft.
4. Pooled-key usage is rate-capped per user and per room, with a kill switch.

## Owned surfaces

Discord owns chat and GitHub owns code, so Agent Rooms must own everything that makes the lineage graph valuable, or it becomes replaceable glue sitting between two platforms that could route around it.

NOW:

- Canonical proposal ids and permalinks.
- The authoritative proposal state machine.
- Cross-room contributor identity.
- The lineage graph and adoption events.
- Room and project identity, including adoption authority.
- Durable proposal Q&A on the proposal page.
- Immutable proposal versions and portable adoption receipts.
- Exportable proposal manifests, with the manifest schema published publicly early as a reference format. The bundle initialization contract is the hard object here, so it should be owned in public.

v0.1:

- Public contribution profiles with embeddable credit chains, since credit that cannot leave Discord is not reputation.
- Post-merge survival analytics, meaning merge-follow and "still in tree N days later," computed by Agent Rooms.

LATER (schema-ready, build deferred):

- Discovery and subscription edges: watching projects, following builders, finding independently adopted work.

## Model policy

The product is provider-neutral: cards record what an agent produced, not which lab made the agent, and any MCP-capable or CLI-driven agent is a first-class citizen.

Hosted inference, when offered, is a transparent menu in three tiers: a near-free tier on a cheap capable open-weight model, in the DeepSeek V4-Flash class, verified July 2026 at $0.14 per million input tokens and $0.28 per million output tokens; a value tier in the roughly $1 input and $4 output per million token band, covering models such as GLM-5.2, Kimi K2.7 Code, and DeepSeek V4-Pro; and a frontier tier covering Claude, GPT, Grok, and the Kimi K3 class. The three-tier menu describes the eventual product; v0 ships exactly one hosted model, from the near-free tier, in the sidebar.

Chinese open-weight models can be served from non-Chinese infrastructure at no price penalty. Verified July 2026: DeepInfra serves DeepSeek V4-Flash from US datacenters at first-party price, and Nebius serves the same roster from EU infrastructure. Inference location is therefore a per-room setting with a visible label, not a silent default.

A platform built on provenance for code is transparent about provenance for inference, so every room displays which model and which infrastructure its hosted inference uses.

## Reputation design (v0.1+, design only)

Weight independent validation: distinct adopting maintainers, adoption across unrelated rooms, adopted descendants, and contributions that survive later versions. Discount self-forks, reciprocal adoption, and trivial remixes. Remix note text is never an input to this score.

## Open questions

- Identity model for public rooms: whether participation requires accounts or anonymous participation is supported.
- Payload size limits and blob storage choice for content-addressed proposal payloads.
- Whether preview-link promotes need snapshotting to guard against link rot, since a live link can change or disappear after promotion.
- Abuse review flow when a revoked or superseded proposal was already forked into someone's workspace before the change.
- Exact license notice mechanics for adopted content in public rooms, beyond the Room-level default license field.
- Exact secret-scanning tooling choice.
- Manifest schema versioning policy.
- How redaction interacts with already-forked copies of a leaked note.
