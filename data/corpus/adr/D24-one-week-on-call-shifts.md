# ADR D24: One-week on-call shifts

- Status: accepted
- Date: 2025-01-10
- Owner: Marcus Chen (SRE)
- Systems: infra

## Context

Only four engineers are trained for on-call. Shorter shifts would put each of them on call every other week, which is worse than one full week in four.

Stated premises:

- Only four engineers are trained for on-call. (fact)

## Decision

On-call rotates weekly among the trained engineers.

## Alternatives considered

- Follow-the-sun with contractors (rejected: cost)

## Consequences

Shifts run Monday to Monday. Training more engineers for on-call is the way to shorten them.
