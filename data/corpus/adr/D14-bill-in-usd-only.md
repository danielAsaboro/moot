# ADR D14: Bill in USD only

- Status: accepted
- Date: 2024-06-20
- Owner: Tomi Adeyemi (CTO)
- Systems: billing

## Context

- Multi-currency billing is not enabled on our Stripe account.

## Decision

All invoices are issued in US dollars regardless of customer location.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
