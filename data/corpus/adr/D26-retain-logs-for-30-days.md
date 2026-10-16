# ADR D26: Retain logs for 30 days

- Status: accepted
- Date: 2024-08-01
- Owner: Marcus Chen (SRE)
- Systems: infra

## Context

- Log storage costs about $0.50 per GB a month.

## Decision

Application logs are deleted after 30 days.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
