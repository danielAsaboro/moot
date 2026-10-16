# ADR D03: Reject photos over 8 MB in the mobile app

- Status: accepted
- Date: 2025-04-12
- Owner: Sofia Rossi (Frontend lead)
- Systems: mobile-app

## Context

- The API gateway enforces a 10 MB request body limit.

## Decision

The mobile app refuses photos over 8 MB before upload and asks the user to pick a smaller one.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
