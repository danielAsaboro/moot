# ADR D14: Bill in USD only

- Status: accepted
- Date: 2024-06-20
- Owner: Tomi Adeyemi (CTO)
- Systems: billing

## Context

Multi-currency billing is not enabled on our Stripe account. Enabling it means a new contract, tax reviews per currency, and reconciliation work finance is not staffed for.

Stated premises:

- Multi-currency billing is not enabled on our Stripe account. (fact)

## Decision

All invoices are issued in US dollars regardless of customer location.

## Alternatives considered

- Invoice in EUR for EU customers via a second Stripe account (rejected: two sets of books)

## Consequences

Every invoice is in USD. Sales should set expectations early in EU deals.
