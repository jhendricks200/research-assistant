---
title: 'Agent Rooms: README'
source_type: article
status: published
topics: [Agent Rooms]
tags: [overview, architecture]
entities: [Agent Rooms]
---
# Agent Rooms (working name)

A selective publishing and remix layer for people who build with private AI agents. Promote, fork, remix, adopt.

Everyone works with their own agent in private. Promote publishes a proposal card into a group space. Others fork the card into a fresh private workspace, remix it, and promote again with lineage intact. Adoption merges the winner into the canonical build with the full credit chain permanently visible.

The hypothesis, stated plainly: proposal cards must materially lower the cost of understanding and improving someone else's agent output compared to pasting diffs in Discord next to a GitHub PR. If they do not, lineage just records activity.

What exists today is a single-room web app: Next.js, Postgres, a GitHub App, and a sidebar agent served through OpenRouter. Signing in with GitHub gives each builder a private agent beside the room chat. Promote opens a real pull request on the room's linked repository. Fork hands another builder the proposal as a five-part bundle. Adopt is a maintainer merging that pull request at the exact commit that was promoted, so the merged code carries a credit trail back to its author and its forks. An unattended smoke test drove the whole loop with five agent personas: 24 pull requests opened, 12 merged, 12 forks, 12 adoptions (`app/stage0-results.json`).

## Where to start reading

[REVIEWERS.md](REVIEWERS.md) maps every file, states the five load-bearing claims with their exact locations, explains how to run and verify, and lists the known gaps. [docs/design/promote-provenance.md](docs/design/promote-provenance.md) is the data model and its invariants. [docs/decisions/](docs/decisions/) holds the three decision records, including why v0 became a web app instead of the Discord bot first planned.

## Running it

```bash
cd app
cp .env.example .env      # then set DATABASE_URL to a local Postgres
npm install
npm run db:migrate
npm run seed              # a demonstration room
DEV_IDENTITY_FALLBACK=1 npm run dev
npm run test              # runs against the same local Postgres
```

This repository is a snapshot of a private working repository, published without its commit history. The plan for the human validation sessions is left out on purpose while those sessions run, so that participants cannot read what is being measured.
