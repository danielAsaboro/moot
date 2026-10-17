# ADR D27: Manage all infrastructure with Terraform

- Status: accepted
- Date: 2024-07-01
- Owner: Marcus Chen (SRE)
- Systems: infra

## Context

SOC 2 requires infrastructure to be reproducible from code. Resources created in the console cannot be shown to be reproducible, and we had drift between staging and production that nobody could explain.

Stated premises:

- SOC 2 requires infrastructure to be reproducible from code. (constraint)
  This holds because we need SOC 2 certification to sell to enterprise customers.

## Decision

No cloud resource is created by hand; everything goes through Terraform.

## Alternatives considered

- CloudFormation (rejected: the team knows Terraform)

## Consequences

No console changes. Every resource is in Terraform with a reviewed plan. Break-glass changes are reverted into code within a day.
