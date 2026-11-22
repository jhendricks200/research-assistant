---
title: 'Agent Rooms: codebase working rules'
source_type: reference
status: published
topics: [Agent Rooms]
tags: [conventions, dev workflow]
entities: [Agent Rooms, Claude Code]
---
# Agent Rooms

Read `REVIEWERS.md` first. It maps every file, states the five load-bearing claims with their exact locations, explains how to run and verify, and lists known gaps honestly. This file is the working context that document does not carry: why things are the way they are, and what will bite you.

## What this is

Rooms where builders chat together, each with a private AI agent in a sidebar. A promote gesture publishes agent output as a proposal, which opens a real pull request on the room's linked GitHub repo. Others fork a proposal into their own workspace, remix it, and the room adopts winners via a SHA-pinned merge that records credit lineage.

The product thesis, and the thing being tested: proposal cards must materially lower the cost of understanding and improving someone else's agent output, compared with pasting diffs into Discord next to a pull request. If they do not, lineage merely records activity. Everything else is in service of asking that question honestly.

## Decisions that are settled, do not relitigate

Audience is open-internet builder pods, not enterprise, because work-team agent collaboration is where GitHub, Cursor, and Anthropic close fastest. GitHub is the canonical build; git is the only version history, and adopt means merging a real PR. The private-to-shared boundary is the product, so every crossing is explicit and recorded. Green is reserved for adoption and passing builds, never decoration. Design direction is "Signal lab", locked, with the component library in `design/ds/` and `design/direction-c2.html` as the reference composition. ADRs in `docs/decisions/` explain the pivots; ADR 0003 is why v0 is a polished single-room web app rather than the Discord bot originally planned.

## Verification discipline, learned the hard way

Two external audits (Codex and Grok) found roughly two dozen real defects across two rounds, including an account-takeover path through username reuse, adoptions recordable without a merge, and a path deny-list that a leading `./` walked straight past. Every one was verified against the code before being fixed, and several reviewer claims were narrower than stated. Do the same: verify claims against the code, and verify your own work by exercising it rather than by reading it. "The tests pass" is not the same as "I drove it in a browser and watched it happen."

When you delegate, tell subagents explicitly not to spawn their own subagents and not to report that work is running in the background. Several did exactly that and stalled silently, once corrupting the working tree mid-rename. Check git state or file timestamps rather than trusting a report.

## Operational gotchas

Run the dev server detached (`nohup ... & disown`) or killing a foreground command takes it down with it. A full Stage 0 run exceeds a ten-minute foreground timeout, so background it. `vercel env run` loads the local `.env` and it wins over pulled production variables, which will silently point a migration at localhost and report success; pass `DATABASE_URL` explicitly and print the target host before any write. The public production alias is `<production-host>`; the `<team-alias>` alias sits behind Vercel SSO and will show testers a login wall.

Dev-only escape hatches exist and must never reach production: `DEV_IDENTITY_FALLBACK` resolves unauthenticated requests to a seeded contributor, and `STAGE0_IDENTITY_OVERRIDE` lets the Stage 0 harness name its acting persona by header. Both require `NODE_ENV=development`, and both are refused on a Vercel deployment whatever `NODE_ENV` says (`onHostedDeployment` in `app/src/lib/session.ts`). Confirm they are absent from production, not merely set to zero.

## Where things stand

The loop works end to end and is deployed. Real GitHub sign-in works, keyed on the immutable numeric GitHub account id. Stage 0, the agent smoke test, ran twelve of twelve clean: twenty-four pull requests opened, twelve merged, twelve forks, twelve adoptions, about three cents. The demo room is curated from real Stage 0 chains with resolving PR links and a genuinely rejected proposal.

Next is validation with people recruited cold from the open internet. The protocol and its pass criteria are kept out of this repository while the test runs, so that participants cannot read what is being measured. Note that Stage 0 cannot answer the payload question and its arm was removed for that reason; agents comply, humans choose.
