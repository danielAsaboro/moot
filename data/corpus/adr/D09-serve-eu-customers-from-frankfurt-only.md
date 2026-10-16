# ADR D09: Serve EU customers from Frankfurt only

- Status: accepted
- Date: 2025-07-01
- Owner: Ada Okafor (Platform lead)
- Systems: infra

- Supersedes: ADR D28

## Context

The EU data residency question comes up in every enterprise deal. All EU customers are in Germany and Austria, so one region in Frankfurt covers residency and keeps latency under 30 ms for every EU tenant we have.

Stated premises:

- All EU customers are in Germany and Austria. (fact)

## Decision

A single EU region in Frankfurt serves all EU tenants.

## Alternatives considered

- Frankfurt plus Paris (rejected: doubles the infrastructure cost for no current customer)
- EU tenants in us-east-1 with contractual promises (rejected by legal)

## Consequences

All EU tenants are provisioned in eu-central-1. A second EU region needs a new ADR.
