# ADR D12: Store sessions in Redis

- Status: accepted
- Date: 2024-07-15
- Owner: Priya Natarajan (Backend engineer)
- Systems: auth

## Context

- The web tier must stay stateless so it can autoscale.

## Decision

Web sessions live in Redis, never in process memory.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
