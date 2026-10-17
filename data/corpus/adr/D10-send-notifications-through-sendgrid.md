# ADR D10: Send notifications through SendGrid

- Status: accepted
- Date: 2024-08-10
- Owner: Priya Natarajan (Backend engineer)
- Systems: notifications

## Context

We send password resets, invoices and a weekly digest. Notification volume is under 100 emails a day, inside the SendGrid free tier. Building on the free plan means no procurement and no contract to review.

Stated premises:

- Notification volume is under 100 emails a day, inside the SendGrid free tier. (fact)
  This holds because tooling and infrastructure spend must stay under $20,000 a month.

## Decision

All transactional email goes through SendGrid on the free plan.

## Alternatives considered

- SES (rejected: deliverability setup took longer than the whole integration)

## Consequences

All transactional mail goes through SendGrid. Volume is reported monthly; the free tier is the budget.
