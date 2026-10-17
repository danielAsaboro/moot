# ADR D17: Use LaunchDarkly for feature flags

- Status: accepted
- Date: 2025-06-10
- Owner: Marcus Chen (SRE)
- Systems: web-app

## Context

Our flag table has no audit log, no targeting rules and no kill switch UI. LaunchDarkly costs under $500 a month at our seat count, which is cheaper than the engineer-week a year we spend on the table.

Stated premises:

- LaunchDarkly costs under $500 a month at our seat count. (fact)
  This holds because tooling and infrastructure spend must stay under $20,000 a month.

## Decision

Feature flags are managed in LaunchDarkly rather than a home-grown table.

## Alternatives considered

- Unleash self-hosted (rejected: another service to run)
- Keep the table and add an admin UI (rejected: see cost)

## Consequences

Flags move to LaunchDarkly; the table is read-only until migrated. Revisit if the bill grows past the budget.
