# ADR D18: Manual QA sign-off before every release

- Status: accepted
- Date: 2024-11-01
- Owner: Sofia Rossi (Frontend lead)
- Systems: web-app

## Context

There is no end-to-end test coverage of the web app, so a release can break checkout without any test noticing. Until there is coverage, a person walks the checklist in staging.

Stated premises:

- There is no end-to-end test coverage of the web app. (fact)

## Decision

A person walks the release checklist in staging before each production release.

## Alternatives considered

- Ship behind flags and monitor (rejected: checkout cannot be flagged per user)

## Consequences

Every production release of the web app has a signed-off checklist in the release ticket. This is a stopgap; the end-to-end suite is the real fix.
