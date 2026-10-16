# ADR D11: Require two reviewers on every pull request

- Status: accepted
- Date: 2024-10-01
- Owner: Tomi Adeyemi (CTO)
- Systems: infra

## Context

Bugs are reaching production that a second pair of eyes would have caught. CI runs no automated test suite; until it does, review is the only gate we have.

Stated premises:

- CI runs no automated test suite. (fact)

## Decision

Every PR needs two approvals before merge.

## Alternatives considered

- One reviewer plus a checklist (rejected: the checklist was being rubber-stamped)

## Consequences

Branch protection requires two approvals. Expect slower merges; pair on reviews to keep the queue short.
