# ADR D03: Reject photos over 8 MB in the mobile app

- Status: accepted
- Date: 2025-04-12
- Owner: Sofia Rossi (Frontend lead)
- Systems: mobile-app

## Context

Photos from recent phones are 12 to 20 MB. The API gateway enforces a 10 MB request body limit, and a rejected request on a mobile connection wastes the user's data and their patience. Rejecting on the device, with an explanation, is kinder than failing after the upload.

Stated premises:

- The API gateway enforces a 10 MB request body limit. (constraint)

## Decision

The mobile app refuses photos over 8 MB before upload and asks the user to pick a smaller one.

## Alternatives considered

- Downscale on device (deferred: the image pipeline team wants originals)
- Chunked upload (rejected: the mobile SDK does not support it)

## Consequences

Photos over 8 MB are refused in the picker with a message. The 8 MB number leaves headroom under the gateway limit for the multipart envelope.
