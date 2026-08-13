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

Use the original ticket, triage category and priority, KB outcome, and support-ticket reference.

## Allowed tools

- MCP tool `escalate_l2`

## Decision rules

- Produce a concise factual problem summary.
- Include the support-ticket reference in the tool call.
- Consider escalation successful only after MCP returns a valid successful result.

## Expected output

Request `escalate_l2` with `summary` and `ticket_reference`.

## Constraints / forbidden behavior

Do not invent diagnosis, logs, attempted fixes, root cause, or impact. Do not claim success before the tool succeeds. Do not mutate lifecycle state; the deterministic application layer owns transitions.
