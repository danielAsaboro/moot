# ADR D05: Use Postgres for every storage need

- Status: accepted
- Date: 2024-06-01
- Owner: Tomi Adeyemi (CTO)
- Systems: infra

## Context

_No context was recorded for this decision._

## Decision

No new datastore is introduced; queues, caches and documents all live in Postgres.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
