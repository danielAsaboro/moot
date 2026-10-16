# ADR D01: Cap file uploads at 10 MB

- Status: accepted
- Date: 2025-02-10
- Owner: Ada Okafor (Platform lead)
- Systems: uploads-api

## Context

Support has been fielding failed uploads for weeks. The failures are confusing because the request looks accepted and then dies somewhere behind the edge: All file uploads pass through the API gateway, so anything over the gateway's limit is dropped with a bare 413 and no application error. Rather than chase each report we want one clear rule at the API.

Stated premises:

- All file uploads pass through the API gateway. (fact)
  This holds because the API gateway enforces a 10 MB request body limit.

## Decision

Reject any upload over 10 MB at the API with a clear error instead of letting it fail downstream.

## Alternatives considered

- Stream uploads directly to S3 with presigned URLs (rejected: two weeks of work for a problem we can rule out today)
- Raise the gateway limit (rejected: the platform team owns Envoy and does not want per-route exceptions)

## Consequences

The uploads API returns a 413 with a readable message at 10 MB. The mobile and web clients should check size before sending. If the gateway limit ever changes this cap should be revisited, because it exists only to mirror it.
