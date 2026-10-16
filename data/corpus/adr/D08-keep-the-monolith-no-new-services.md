# ADR D08: Keep the monolith; no new services

- Status: accepted
- Date: 2025-05-20
- Owner: Tomi Adeyemi (CTO)
- Systems: infra

## Context

There is a recurring proposal to extract the billing and notifications code into services. The engineering team is under 15 people. At that size the coordination cost of services (contracts, deploys, on-call surface) outweighs the autonomy they buy. The monolith's modules already have clear owners.

Stated premises:

- The engineering team is under 15 people. (fact)

## Decision

New features are built inside the monolith; service extraction proposals are declined.

## Alternatives considered

- Extract billing only (rejected: it is the most entangled module)
- Modular monolith with enforced boundaries (accepted as part of this decision)

## Consequences

New features go in the monolith. Extraction proposals are declined until the team is large enough that deploy contention is a measured problem.
