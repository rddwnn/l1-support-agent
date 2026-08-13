---
name: triage
description: Classify an incoming L1 support ticket by category and priority. Use before processing a NEW Case.
---

# Triage

## Purpose

Classify a support ticket consistently for downstream processing.

## When to use

Use only for initial triage of a NEW Case.

## Required input/context

Use the ticket title, description, source category, and source priority. Treat source classification as secondary context.

## Allowed tools

None.

## Decision rules

- Choose exactly one category: `access`, `consultation`, `hardware`, `software`, or `network`.
- Choose exactly one priority: `low`, `medium`, `high`, or `critical`.
- Base the decision only on ticket data. Do not invent impact, symptoms, causes, or evidence.
- Do not search the knowledge base or choose an escalation.

## Expected output

Return a structured object with string fields `category`, `priority`, and concise factual `reasoning`.

## Constraints / forbidden behavior

Do not call tools, mutate Case state, use external facts, or return vocabulary outside the allowed values.
