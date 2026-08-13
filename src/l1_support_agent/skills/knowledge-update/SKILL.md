---
name: knowledge-update
description: Propose new KB instructions from a solved and verified infrastructure or software support case after human verification.
---

# Knowledge Update

## Purpose

Turn a verified resolution into a reusable knowledge article proposal.

## When to use

Use only for solved and verified infrastructure or software cases selected for knowledge capture.

## Required input/context

Require the original problem context, verified resolution, category, and existing KB search results.

## Allowed tools

None. Python searches and writes the KB directly in this trusted application workflow; no normal agent KB-write tool exists.

## Decision rules

- Reject unresolved, speculative, or unverified cases.
- Evaluate retrieved articles as duplicate candidates, not automatic matches.
- Select structured `skip_existing` only when a returned article adequately covers the verified resolution, and supply its ID.
- Otherwise select structured `create` and supply only a concise article title.
- Treat the caller-provided verified resolution as immutable factual input; never generate or modify it.

## Expected output

Return structured fields `decision`, `existing_article_id`, and `title`. Python deterministically builds and persists any new article from the original problem and verified resolution.

## Constraints / forbidden behavior

Never convert speculation into instructions, invent resolution content, request tools, authorize tools, or mutate Case state. Do not claim a write occurred; Python owns validation and persistence.
