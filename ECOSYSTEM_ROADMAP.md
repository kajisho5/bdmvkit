# Roadmap — bdmvkit

Part of the [AI Video Production OS](https://github.com/kajisho5/AI-video-production-OS/blob/main/docs/ecosystem/ROADMAP.md) ecosystem: department **納品 (Delivery)**, status `active`, optional component.
Written from a read-only audit of this repository on 2026-10-30. Each step below is meant to be one pull request; tick it off by linking the PR.

## Where it stands

v0.7.0, Blu-ray (BDMV) authoring, CLI encode/build. Python 3.11+ stdlib, unittest, CI on Ubuntu + macOS. Optional component (installed with --with-optional). oncemore vendors this library.

## What this repository owns

`ecosystem.json` gives each job to exactly one repository. Work outside this list belongs to its owner and is handed over, not re-implemented.

| Owned job | Status | Note |
|---|---|---|
| Blu-ray作成 | done |  |

## Wiring

Not reachable from the agent; encodes with ffmpeg directly.

## Steps

- [x] **1. (optional) Contract in the OS schema** — skill_id, version, provides[]
  - Done when: validates against the OS schema
- [ ] **2. Proceedings discs for long events** — a bitrate planner for 2-8 h of sessions on BD-25 / BD-50 (quality floor per title stated, a warning when it is not met), one title or chapter per session from a chapter list (slide-sync-skill or the agent's IR), menu entries from session titles. Field review 2026-11-05 (Velisa ROADMAP, third round)
  - なぜ要るか：学会・企業イベントの記録 BD 納品は今も多く、終日分を 1 枚に収める計算が毎回いる
  - Done when: a 6 h chapter list plans within BD-50 with every title above the floor, or reports which is below

## Boundaries

Vendored by oncemore (`oncemore/_vendor/`).

---
Engine for every media operation: [ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill) (42 tools, treated as complete). Orchestrator: [video-production-agent](https://github.com/kajisho5/video-production-agent).
