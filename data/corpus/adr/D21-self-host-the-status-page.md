# ADR D21: Self-host the status page

- Status: accepted
- Date: 2024-12-10
- Owner: Marcus Chen (SRE)
- Systems: infra

## Context

The status page vendor's own outage took our status page down with it, which made for an awkward incident review.

_No premise was recorded for this decision._

## Decision

The public status page runs on our own infrastructure.

## Alternatives considered

- A second vendor (rejected)

## Consequences

The status page is a static site on separate infrastructure, deployed from a separate account.
