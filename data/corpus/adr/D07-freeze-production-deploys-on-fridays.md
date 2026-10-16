# ADR D07: Freeze production deploys on Fridays

- Status: accepted
- Date: 2024-09-05
- Owner: Marcus Chen (SRE)
- Systems: infra

## Context

Two of the last three incidents started with a Friday afternoon deploy and ran into the weekend. A rollback requires a manual database restore, which takes the on-call engineer about forty minutes and needs a second person to verify. On a Friday evening that second person is often unreachable.

Stated premises:

- A rollback requires a manual database restore. (constraint)

## Decision

No production deploy from Friday 12:00 to Monday 09:00.

## Alternatives considered

- Deploy freeze only for schema changes (rejected: too hard to police)
- Automated rollback (deferred: needs the migration tooling first)

## Consequences

No production deploy from Friday 12:00 to Monday 09:00 local time. Hotfixes need the on-call lead's approval.
