# ADR D15: Support Safari 15 and newer only

- Status: accepted
- Date: 2025-03-15
- Owner: Sofia Rossi (Frontend lead)
- Systems: web-app

## Context

We carry a pile of polyfills and CSS workarounds for old Safari. Safari versions below 15 are under 1% of traffic, and the maintenance cost of those workarounds is measured in incidents, not in users.

Stated premises:

- Safari versions below 15 are under 1% of traffic. (fact)

## Decision

The web app drops polyfills and workarounds for Safari below version 15.

## Alternatives considered

- Keep supporting Safari 13 (rejected)

## Consequences

Polyfills for Safari below 15 are removed. The support page states the minimum version.
