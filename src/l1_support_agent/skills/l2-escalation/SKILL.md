---
name: l2-escalation
description: Route an unresolved infrastructure or support problem to L2 after knowledge-base investigation finds no adequate solution.
---

# L2 Escalation

## Purpose

Prepare a factual escalation for an L2 support specialist.

## When to use

Use only after KB investigation found no adequate solution and the problem is infrastructural or otherwise appropriate for L2.

## Required input/context

Use the original ticket, triage category and priority, and KB outcome.

## Allowed tools

- MCP tool `escalate_l2`

## Decision rules

- Select the structured `escalate_l2` outcome.
- Supply a concise factual `summary`.
- Let Python validate the decision, supply the support-ticket reference, and execute the MCP tool.
- Do not assume or report that escalation succeeded.

## Expected output

Return structured post-KB decision fields with `decision` set to `escalate_l2` and a non-empty `summary`.

## Constraints / forbidden behavior

Do not request or call the MCP tool directly. Do not invent diagnosis, logs, attempted fixes, root cause, or impact. Do not claim tool success. Do not mutate lifecycle state; the deterministic Python application layer owns tool execution and transitions.
