---
name: kb-investigation
description: Investigate an actively processing L1 ticket in the knowledge base and assess candidate relevance before resolution.
---

# KB Investigation

## Purpose

Find candidate instructions and determine whether they adequately solve the reported problem.

## When to use

Use while a Case is `PROCESSING`, before clarification or escalation decisions.

## Required input/context

Use the ticket title, description, category, priority, and articles returned during this investigation.

## Allowed tools

- MCP tool `search_kb`

## Decision rules

- Search with the essential symptoms or error message.
- Treat retrieved articles as candidates, not proof of a solution.
- Evaluate semantic relevance after retrieval.
- Resolve only when one article directly addresses the reported problem and contains applicable instructions.
- Ground the user-facing answer only in the selected article.
- If no article is adequate, continue to post-KB routing.

## Expected output

Request `search_kb`, then either select a returned article by ID with a concise grounded answer or continue to post-KB routing.

## Constraints / forbidden behavior

Do not fabricate missing instructions, assumptions, causes, or performed actions. Do not treat a non-empty result list as a confirmed match. This skill does not authorize tools or mutate Case state.
