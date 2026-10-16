# ADR D27: Manage all infrastructure with Terraform

- Status: accepted
- Date: 2024-07-01
- Owner: Marcus Chen (SRE)
- Systems: infra

## Context

- SOC 2 requires infrastructure to be reproducible from code.

## Decision

No cloud resource is created by hand; everything goes through Terraform.

## Consequences

Teams follow this until it is explicitly revisited. Exceptions need the owner's approval.
