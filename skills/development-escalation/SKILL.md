---
name: development-escalation
description: Route an unresolved actual software defect to development after knowledge-base investigation finds no adequate solution.
---

# Development Escalation

## Purpose

Prepare a factual GitHub issue for a software defect that L1 cannot resolve from the KB.

## When to use

Use only after KB investigation found no adequate solution and the ticket describes an actual software defect.

## Required input/context

Use the ticket title and description, factual technical context, metadata errors/logs when present, and support-ticket reference.

## Allowed tools

- MCP tool `create_github_issue`

## Decision rules

- Produce a useful issue title and factual technical context.
- Preserve the original support-ticket description.
- Include only errors or logs actually present in ticket metadata; otherwise state that they were not provided.
- Include the support-ticket reference.
- Consider creation successful only after MCP returns a valid non-empty issue URL.

## Expected output

Request `create_github_issue` with `title`, `technical_context`, `ticket_description`, `errors_logs`, and `ticket_reference`.

## Constraints / forbidden behavior

Never invent logs, stack traces, reproduction steps, diagnosis, or diagnostic evidence. Do not claim success before receiving a valid issue URL. Do not mutate lifecycle state; the deterministic application layer owns transitions.
