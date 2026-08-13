---
name: l2-escalation
description: Route an unresolved non-development support problem to L2 after knowledge-base investigation finds no adequate solution.
---

# L2 Escalation

## Purpose

Prepare a factual escalation for an L2 support specialist.

## When to use

Use after KB investigation found no adequate solution and the case is not an actual software defect requiring development. L2 is the fallback for unresolved hardware, network, access, operational, consultation, infrastructure, and ambiguous support requests.

## Required input/context

Use the original ticket, triage category and priority, and KB outcome.

## Allowed tools

- MCP tool `escalate_l2`

## Decision rules

- Select the structured `escalate_l2` outcome.
- Supply a concise factual `summary`.
- Do not select L2 for a reported software malfunction that qualifies for development escalation.
- Do not invent a diagnosis merely to select this fallback route.
- Let Python validate the decision, supply the support-ticket reference, and execute the MCP tool.
- Do not assume or report that escalation succeeded.

## Expected output

Return structured post-KB decision fields with `decision` set to `escalate_l2` and a non-empty `summary`.

## Constraints / forbidden behavior

Do not request or call the MCP tool directly. Do not invent diagnosis, logs, attempted fixes, root cause, or impact. Do not claim tool success. Do not mutate lifecycle state; the deterministic Python application layer owns tool execution and transitions.
