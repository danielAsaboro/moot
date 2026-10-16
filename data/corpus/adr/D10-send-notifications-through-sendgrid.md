# ADR D10: Send notifications through SendGrid

- Status: accepted
- Date: 2024-08-10
- Owner: Priya Natarajan (Backend engineer)
- Systems: notifications

## Context

- Notification volume is under 100 emails a day, inside the SendGrid free tier.

## Decision

All transactional email goes through SendGrid on the free plan.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
