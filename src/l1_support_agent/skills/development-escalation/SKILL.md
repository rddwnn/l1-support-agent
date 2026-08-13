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

Use the ticket title and description, triage result, and KB outcome.

## Allowed tools

- MCP tool `create_github_issue`

## Decision rules

- Select the structured `create_github_issue` outcome.
- Supply a useful `issue_title` and factual `technical_context`.
- Let Python validate the decision and supply the original ticket description, available metadata errors/logs, and support-ticket reference.
- Let Python execute the MCP tool and validate its returned issue URL.
- Do not assume or report that issue creation succeeded.

## Expected output

Return structured post-KB decision fields with `decision` set to `create_github_issue`, a non-empty `issue_title`, and non-empty `technical_context`.

## Constraints / forbidden behavior

Do not request or call the MCP tool directly. Never invent logs, stack traces, reproduction steps, diagnosis, or diagnostic evidence. Do not fabricate fields or claim issue creation succeeded. Do not mutate lifecycle state; the deterministic Python application layer owns tool execution and transitions.
