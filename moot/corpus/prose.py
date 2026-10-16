"""Hand-written prose for the Larkspur ADRs, so the corpus reads like a company wrote it.

Each entry: context paragraphs (with {p0}, {p1} placeholders where the stated premises go, verbatim, so the
extractor's span check can find them), the alternatives that were considered, and the specific consequences.
The spec in spec.py stays the single source of truth for ids, dates, premises and verdicts; this file only
dresses it.
"""

ADR = {
    "D01": dict(
        context="Support has been fielding failed uploads for weeks. The failures are confusing because the request looks accepted and then dies "
                "somewhere behind the edge: {p0}, so anything over the gateway's limit is dropped with a bare 413 and no application error. "
                "Rather than chase each report we want one clear rule at the API.",
        alternatives=["Stream uploads directly to S3 with presigned URLs (rejected: two weeks of work for a problem we can rule out today)",
                      "Raise the gateway limit (rejected: the platform team owns Envoy and does not want per-route exceptions)"],
        consequences="The uploads API returns a 413 with a readable message at 10 MB. The mobile and web clients should check size before sending. "
                     "If the gateway limit ever changes this cap should be revisited, because it exists only to mirror it."),
    "D02": dict(
        context="Customer CSV imports regularly run to 40 or 50 MB. {p0}, so a single request cannot carry them. We do not want to run a "
                "separate ingestion endpoint outside the gateway.",
        alternatives=["SFTP drop (rejected: customers hate it and support hates it more)", "Compress before upload (rejected: still over the limit for the large accounts)"],
        consequences="The import client splits files into 5 MB parts with a manifest; the pipeline reassembles and validates row counts. "
                     "Partial imports are retried per part."),
    "D03": dict(
        context="Photos from recent phones are 12 to 20 MB. {p0}, and a rejected request on a mobile connection wastes the user's data and "
                "their patience. Rejecting on the device, with an explanation, is kinder than failing after the upload.",
        alternatives=["Downscale on device (deferred: the image pipeline team wants originals)", "Chunked upload (rejected: the mobile SDK does not support it)"],
        consequences="Photos over 8 MB are refused in the picker with a message. The 8 MB number leaves headroom under the gateway limit for the multipart envelope."),
    "D04": dict(
        context="The search index drifts from the database within hours because partial updates fail on the nested fields. "
                "{p0}; the mapping change that would allow them is a multi-week migration nobody can staff this quarter.",
        alternatives=["Fix the mapping now (deferred to Q1)", "Dual-write with a reconciliation job (rejected: more moving parts than the problem deserves)"],
        consequences="A nightly job at 02:00 UTC drops and rebuilds the index. Search results can be up to a day stale. Revisit when the mapping migration lands."),
    "D05": dict(
        context="We keep adding infrastructure. Every new datastore is another thing to back up, monitor, and explain to the auditor.",
        alternatives=["Redis for queues, S3 for documents (rejected)"],
        consequences="Queues use SKIP LOCKED tables, caches are unlogged tables, documents are JSONB. Exceptions need a written ADR."),
    "D06": dict(
        context="{p0}. Our keys currently never expire, which came up as a finding in the readiness assessment.",
        alternatives=["Rotate on demand only (rejected: fails the control)"],
        consequences="Keys carry an expiry; the auth service refuses expired keys; customers get a reminder at 14 and 3 days."),
    "D07": dict(
        context="Two of the last three incidents started with a Friday afternoon deploy and ran into the weekend. {p0}, which takes the on-call "
                "engineer about forty minutes and needs a second person to verify. On a Friday evening that second person is often unreachable.",
        alternatives=["Deploy freeze only for schema changes (rejected: too hard to police)", "Automated rollback (deferred: needs the migration tooling first)"],
        consequences="No production deploy from Friday 12:00 to Monday 09:00 local time. Hotfixes need the on-call lead's approval."),
    "D08": dict(
        context="There is a recurring proposal to extract the billing and notifications code into services. {p0}. At that size the coordination "
                "cost of services (contracts, deploys, on-call surface) outweighs the autonomy they buy. The monolith's modules already have clear owners.",
        alternatives=["Extract billing only (rejected: it is the most entangled module)", "Modular monolith with enforced boundaries (accepted as part of this decision)"],
        consequences="New features go in the monolith. Extraction proposals are declined until the team is large enough that deploy contention is a measured problem."),
    "D09": dict(
        context="The EU data residency question comes up in every enterprise deal. {p0}, so one region in Frankfurt covers residency and keeps latency "
                "under 30 ms for every EU tenant we have.",
        alternatives=["Frankfurt plus Paris (rejected: doubles the infrastructure cost for no current customer)", "EU tenants in us-east-1 with contractual promises (rejected by legal)"],
        consequences="All EU tenants are provisioned in eu-central-1. A second EU region needs a new ADR."),
    "D10": dict(
        context="We send password resets, invoices and a weekly digest. {p0}. Building on the free plan means no procurement and no contract to review.",
        alternatives=["SES (rejected: deliverability setup took longer than the whole integration)"],
        consequences="All transactional mail goes through SendGrid. Volume is reported monthly; the free tier is the budget."),
    "D11": dict(
        context="Bugs are reaching production that a second pair of eyes would have caught. {p0}; until it does, review is the only gate we have.",
        alternatives=["One reviewer plus a checklist (rejected: the checklist was being rubber-stamped)"],
        consequences="Branch protection requires two approvals. Expect slower merges; pair on reviews to keep the queue short."),
    "D12": dict(
        context="{p0}. Sticky sessions on the load balancer kept biting us during deploys, when an instance drained and its users were logged out.",
        alternatives=["Signed cookies only (rejected: we need server-side revocation)"],
        consequences="Sessions live in Redis with a 30-day TTL. Any instance can serve any request; deploys no longer log users out."),
    "D13": dict(
        context="Enterprise customers ask for encryption with keys we control. {p0}, so database-level encryption cannot satisfy that today.",
        alternatives=["Move to a region where RDS supports CMK (rejected: residency)", "Wait for AWS (rejected: no date)"],
        consequences="The application encrypts PII columns with per-tenant keys from KMS before writing. Searching on encrypted columns is not possible; design around it."),
    "D14": dict(
        context="{p0}. Enabling it means a new contract, tax reviews per currency, and reconciliation work finance is not staffed for.",
        alternatives=["Invoice in EUR for EU customers via a second Stripe account (rejected: two sets of books)"],
        consequences="Every invoice is in USD. Sales should set expectations early in EU deals."),
    "D15": dict(
        context="We carry a pile of polyfills and CSS workarounds for old Safari. {p0}, and the maintenance cost of those workarounds is measured in incidents, not in users.",
        alternatives=["Keep supporting Safari 13 (rejected)"],
        consequences="Polyfills for Safari below 15 are removed. The support page states the minimum version."),
    "D16": dict(
        context="{p0}. A log line with an email address in it is personal data in a system with 30-day retention and broad read access.",
        alternatives=["Restrict log access instead (rejected: does not address retention)"],
        consequences="The logging library scrubs known PII fields; a CI check fails on new log calls that pass user objects."),
    "D17": dict(
        context="Our flag table has no audit log, no targeting rules and no kill switch UI. {p0}, which is cheaper than the engineer-week a year we spend on the table.",
        alternatives=["Unleash self-hosted (rejected: another service to run)", "Keep the table and add an admin UI (rejected: see cost)"],
        consequences="Flags move to LaunchDarkly; the table is read-only until migrated. Revisit if the bill grows past the budget."),
    "D18": dict(
        context="{p0}, so a release can break checkout without any test noticing. Until there is coverage, a person walks the checklist in staging.",
        alternatives=["Ship behind flags and monitor (rejected: checkout cannot be flagged per user)"],
        consequences="Every production release of the web app has a signed-off checklist in the release ticket. This is a stopgap; the end-to-end suite is the real fix."),
    "D19": dict(
        context="Running the pipeline continuously looked attractive for freshness, but {p0}, and our warehouse bill tripled in the month we tried it.",
        alternatives=["Micro-batches every 5 minutes (rejected: same cost shape)", "Streaming into a cheaper store (deferred)"],
        consequences="The pipeline runs hourly. Dashboards can be up to an hour behind. Revisit if the warehouse pricing model changes."),
    "D20": dict(
        context="React Native 0.74 defaults to the New Architecture. {p0}, and payments are the one part of the app we cannot ship without.",
        alternatives=["Fork the SDK (rejected: unmaintainable)", "Web checkout in a webview (rejected: conversion drop)"],
        consequences="The app stays on 0.72 with the old architecture until the payments vendor ships support. Track their release notes."),
    "D21": dict(
        context="The status page vendor's own outage took our status page down with it, which made for an awkward incident review.",
        alternatives=["A second vendor (rejected)"],
        consequences="The status page is a static site on separate infrastructure, deployed from a separate account."),
    "D22": dict(
        context="{p0}, and the same control expects access to be reviewed. We currently review access when someone leaves, which the auditor flagged as insufficient.",
        alternatives=["Quarterly review (rejected: fails the control)"],
        consequences="A monthly ticket lists every production grant; owners confirm or revoke within a week."),
    "D23": dict(
        context="Serial integer keys collide the moment data moves between databases. {p0}, and merging per-tenant tables with overlapping integer ids would be a migration from hell.",
        alternatives=["Snowflake-style ids (rejected: needs a coordinator service)", "ULIDs (deferred: no library we trusted at the time)"],
        consequences="Every new table uses UUIDv4 primary keys. Index bloat is accepted. Revisit if the sharding plan changes."),
    "D24": dict(
        context="{p0}. Shorter shifts would put each of them on call every other week, which is worse than one full week in four.",
        alternatives=["Follow-the-sun with contractors (rejected: cost)"],
        consequences="Shifts run Monday to Monday. Training more engineers for on-call is the way to shorten them."),
    "D25": dict(
        context="{p0}: last month 80% of new accounts were bots creating workspaces to host spam. Captchas slowed them for a week.",
        alternatives=["Email verification plus rate limits (rejected: tried, bypassed)", "Paid-only sign-up (rejected: kills trials)"],
        consequences="The sign-up form is disabled; sales creates accounts. Marketing is told conversion from the site will drop."),
    "D26": dict(
        context="{p0}, and we were storing eighteen months of logs nobody read. The last three incidents used logs from the previous day.",
        alternatives=["90 days (rejected: cost)", "Cold storage after 30 days (deferred)"],
        consequences="Logs are deleted after 30 days. Security events are exported separately with longer retention."),
    "D27": dict(
        context="{p0}. Resources created in the console cannot be shown to be reproducible, and we had drift between staging and production that nobody could explain.",
        alternatives=["CloudFormation (rejected: the team knows Terraform)"],
        consequences="No console changes. Every resource is in Terraform with a reviewed plan. Break-glass changes are reverted into code within a day."),
    "D28": dict(
        context="We have no EU customers yet and one region is simpler to run.",
        alternatives=[],
        consequences="Everything runs in us-east-1."),
    "D29": dict(
        context="Support is one person part time.",
        alternatives=["Intercom (rejected: cost)"],
        consequences="A shared inbox with a 1-business-day target."),
    "D30": dict(
        context="{p0}. The embed widget relies on a third-party cookie to keep users signed in across customer sites, and that will simply stop working.",
        alternatives=["Storage Access API prompts (rejected: too many prompts per session)"],
        consequences="The widget uses first-party storage with a short-lived token exchange. Expect more sign-in prompts on customer sites."),
}

PR_TEMPLATE = """## Summary

{text}

## Changes

{changes}

## Testing

{testing}

Reviewers: {reviewers}
"""

CHAT_REPLIES = {
    # evidence id -> follow-up messages in the same thread: (author id, text)
    "chat-2025-10-02-search": [("priya", "Ouch. Is the nightly job still in place or do we need to re-enable it?"), ("lena", "Still there, never removed. Leaving it as the source of truth for now.")],
    "chat-2026-05-16-farewell": [("tomi", "Thank you Ada. Platform decisions move to me for now; I will go through the ADRs you owned."), ("marcus", "Safe travels!")],
    "chat-2026-01-08-standup": [("sofia", "So Friday deploys are back on the table?"), ("marcus", "Technically yes. The freeze ADR still says no, so let us talk about it in planning.")],
    "chat-2026-07-09-ld": [("tomi", "That is more than double the budget in the ADR. Can we drop seats?"), ("marcus", "Seats are already minimal. It is the MAU-based pricing change.")],
    "chat-2026-08-15-ld": [("marcus", "Good news, thanks for pushing on it.")],
    "chat-2026-02-26-hiring": [("jonah", "Welcome aboard, both of you.")],
    "chat-2026-06-05-retro": [("priya", "Agreed, let us write it down this time.")],
    "chat-2025-08-21-ci": [("tomi", "Finally. Does that mean we can relax the two-reviewer rule?"), ("marcus", "Separate conversation, but probably.")],
}
