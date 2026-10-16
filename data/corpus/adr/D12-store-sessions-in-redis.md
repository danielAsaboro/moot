# ADR D12: Store sessions in Redis

- Status: accepted
- Date: 2024-07-15
- Owner: Priya Natarajan (Backend engineer)
- Systems: auth

## Context

The web tier must stay stateless so it can autoscale. Sticky sessions on the load balancer kept biting us during deploys, when an instance drained and its users were logged out.

Stated premises:

- The web tier must stay stateless so it can autoscale. (constraint)

## Decision

Web sessions live in Redis, never in process memory.

## Alternatives considered

- Signed cookies only (rejected: we need server-side revocation)

## Consequences

Sessions live in Redis with a 30-day TTL. Any instance can serve any request; deploys no longer log users out.
