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

No KB write tool exists in this branch. Search existing KB coverage before proposing an article.

## Decision rules

- Reject unresolved, speculative, or unverified cases.
- Check for duplicate or adequate existing KB coverage first.
- Include a clear title, problem context, verified resolution instructions, and appropriate category.

## Expected output

Produce a reviewable article proposal; do not write it to the KB.

## Constraints / forbidden behavior

Never convert speculation into instructions, overwrite duplicate coverage, call a nonexistent write tool, authorize tools, or mutate Case state.
