"""Ground-truth specification for the synthetic demo company, Larkspur.

Larkspur is a fictional 30-person B2B SaaS company (2024-2026). Everything here is
invented. The spec is the single source of truth: the corpus generator renders it into
ADRs, tickets, pull requests and chat; the graph builder turns it into graph.json; the
eval scores extraction and retrieval against it.

Edge semantics:
  Decision -BECAUSE_OF-> Premise          the stated reason for the decision
  Premise  -DERIVED_FROM-> Premise         a premise that only holds because another does
  Evidence -SUPPORTS {at}-> Premise        a dated document that affirms the premise
  Evidence -CONTRADICTS {at}-> Premise     a dated document that shows the premise no longer holds
  Person   -OWNS {valid_from, valid_to}-> Decision
  Decision -GOVERNS-> System
  Decision -SUPERSEDES-> Decision
"""

PEOPLE = [
    # id, name, role, joined, left
    ("ada", "Ada Okafor", "Platform lead", "2024-05-01", "2026-05-15"),
    ("tomi", "Tomi Adeyemi", "CTO", "2024-05-01", None),
    ("priya", "Priya Natarajan", "Backend engineer", "2024-06-01", None),
    ("marcus", "Marcus Chen", "SRE", "2024-07-01", None),
    ("lena", "Lena Fischer", "Data engineer", "2024-10-01", None),
    ("jonah", "Jonah Mbeki", "Security engineer", "2024-12-01", None),
    ("sofia", "Sofia Rossi", "Frontend lead", "2024-09-01", None),
    ("kwame", "Kwame Boateng", "Engineering manager", "2025-08-01", None),
]

SYSTEMS = [
    ("uploads-api", "Uploads API"), ("api-gateway", "API gateway"), ("billing", "Billing"),
    ("auth", "Auth"), ("search", "Search"), ("data-pipeline", "Data pipeline"),
    ("web-app", "Web app"), ("mobile-app", "Mobile app"), ("notifications", "Notifications"),
    ("infra", "Infrastructure"),
]

# id -> (text, kind)
PREMISES = {
    "p_gateway_path": ("All file uploads pass through the API gateway", "fact"),
    "p_gateway_limit": ("The API gateway enforces a 10 MB request body limit", "constraint"),
    "p_es_incremental": ("Our Elasticsearch mapping cannot take incremental updates", "constraint"),
    "p_soc2_rotation": ("The SOC 2 auditor requires credential rotation at most every 90 days", "constraint"),
    "p_no_rollback": ("A rollback requires a manual database restore", "constraint"),
    "p_team_size": ("The engineering team is under 15 people", "fact"),
    "p_eu_customers": ("All EU customers are in Germany and Austria", "fact"),
    "p_sendgrid_free": ("Notification volume is under 100 emails a day, inside the SendGrid free tier", "fact"),
    "p_no_ci_tests": ("CI runs no automated test suite", "fact"),
    "p_stateless": ("The web tier must stay stateless so it can autoscale", "constraint"),
    "p_rds_no_cmk": ("RDS does not support customer-managed encryption keys in eu-central-1", "constraint"),
    "p_stripe_multi": ("Multi-currency billing is not enabled on our Stripe account", "fact"),
    "p_safari_share": ("Safari versions below 15 are under 1% of traffic", "fact"),
    "p_gdpr": ("GDPR applies to our EU users", "constraint"),
    "p_ld_budget": ("LaunchDarkly costs under $500 a month at our seat count", "fact"),
    "p_no_e2e": ("There is no end-to-end test coverage of the web app", "fact"),
    "p_warehouse_cost": ("Warehouse query cost scales with how often the pipeline runs", "fact"),
    "p_bq_ondemand": ("We are on BigQuery on-demand pricing", "fact"),
    "p_rn_sdk": ("The payments SDK does not support the React Native New Architecture", "constraint"),
    "p_sharding": ("We plan to shard Postgres by tenant", "assumption"),
    "p_oncall_pool": ("Only four engineers are trained for on-call", "fact"),
    "p_signup_abuse": ("Free-tier bots are abusing public sign-up", "fact"),
    "p_log_cost": ("Log storage costs about $0.50 per GB a month", "fact"),
    "p_iac_soc2": ("SOC 2 requires infrastructure to be reproducible from code", "constraint"),
    "p_chrome_3p": ("Chrome will remove third-party cookies in 2025", "assumption"),
}

# premise -> premise it depends on
DERIVED_FROM = {
    "p_gateway_path": "p_gateway_limit",   # upload cap holds only while the gateway limit holds
    "p_warehouse_cost": "p_bq_ondemand",
}

# Decisions. premises: list of premise ids the ADR states as context.
# expected: the ground-truth verdict as of 2026-10-16.
DECISIONS = [
    dict(id="D01", title="Cap file uploads at 10 MB", decided_on="2025-02-10", owner="ada",
         systems=["uploads-api"], premises=["p_gateway_path"], expected="MOOT",
         summary="Reject any upload over 10 MB at the API with a clear error instead of letting it fail downstream."),
    dict(id="D02", title="Chunk CSV imports into 5 MB parts", decided_on="2025-03-01", owner="priya",
         systems=["data-pipeline"], premises=["p_gateway_limit"], expected="MOOT",
         summary="Split customer CSV imports client-side into 5 MB parts and reassemble them in the pipeline."),
    dict(id="D03", title="Reject photos over 8 MB in the mobile app", decided_on="2025-04-12", owner="sofia",
         systems=["mobile-app"], premises=["p_gateway_limit"], expected="MOOT",
         summary="The mobile app refuses photos over 8 MB before upload and asks the user to pick a smaller one."),
    dict(id="D04", title="Rebuild the search index in full every night", decided_on="2024-11-20", owner="lena",
         systems=["search"], premises=["p_es_incremental"], expected="DISPUTED",
         summary="A nightly job drops and rebuilds the whole search index rather than applying updates."),
    dict(id="D05", title="Use Postgres for every storage need", decided_on="2024-06-01", owner="tomi",
         systems=["infra"], premises=[], expected="UNDOCUMENTED",
         summary="No new datastore is introduced; queues, caches and documents all live in Postgres."),
    dict(id="D06", title="Rotate API keys every 90 days", decided_on="2025-01-15", owner="jonah",
         systems=["auth"], premises=["p_soc2_rotation"], expected="HOLDS",
         summary="All service and customer API keys expire after 90 days and must be rotated."),
    dict(id="D07", title="Freeze production deploys on Fridays", decided_on="2024-09-05", owner="marcus",
         systems=["infra"], premises=["p_no_rollback"], expected="MOOT",
         summary="No production deploy from Friday 12:00 to Monday 09:00."),
    dict(id="D08", title="Keep the monolith; no new services", decided_on="2025-05-20", owner="tomi",
         systems=["infra"], premises=["p_team_size"], expected="MOOT",
         summary="New features are built inside the monolith; service extraction proposals are declined."),
    dict(id="D09", title="Serve EU customers from Frankfurt only", decided_on="2025-07-01", owner="ada",
         systems=["infra"], premises=["p_eu_customers"], expected="MOOT", supersedes="D28",
         summary="A single EU region in Frankfurt serves all EU tenants."),
    dict(id="D10", title="Send notifications through SendGrid", decided_on="2024-08-10", owner="priya",
         systems=["notifications"], premises=["p_sendgrid_free"], expected="HOLDS",
         summary="All transactional email goes through SendGrid on the free plan."),
    dict(id="D11", title="Require two reviewers on every pull request", decided_on="2024-10-01", owner="tomi",
         systems=["infra"], premises=["p_no_ci_tests"], expected="DISPUTED",
         summary="Every PR needs two approvals before merge."),
    dict(id="D12", title="Store sessions in Redis", decided_on="2024-07-15", owner="priya",
         systems=["auth"], premises=["p_stateless"], expected="HOLDS",
         summary="Web sessions live in Redis, never in process memory."),
    dict(id="D13", title="Encrypt PII in the application layer", decided_on="2025-02-01", owner="jonah",
         systems=["billing"], premises=["p_rds_no_cmk"], expected="MOOT",
         summary="PII columns are encrypted by the application with our own keys before they reach the database."),
    dict(id="D14", title="Bill in USD only", decided_on="2024-06-20", owner="tomi",
         systems=["billing"], premises=["p_stripe_multi"], expected="HOLDS",
         summary="All invoices are issued in US dollars regardless of customer location."),
    dict(id="D15", title="Support Safari 15 and newer only", decided_on="2025-03-15", owner="sofia",
         systems=["web-app"], premises=["p_safari_share"], expected="HOLDS",
         summary="The web app drops polyfills and workarounds for Safari below version 15."),
    dict(id="D16", title="Never write PII to logs", decided_on="2024-09-01", owner="jonah",
         systems=["infra"], premises=["p_gdpr"], expected="HOLDS",
         summary="Log lines are scrubbed of personal data before shipping."),
    dict(id="D17", title="Use LaunchDarkly for feature flags", decided_on="2025-06-10", owner="marcus",
         systems=["web-app"], premises=["p_ld_budget"], expected="DISPUTED",
         summary="Feature flags are managed in LaunchDarkly rather than a home-grown table."),
    dict(id="D18", title="Manual QA sign-off before every release", decided_on="2024-11-01", owner="sofia",
         systems=["web-app"], premises=["p_no_e2e"], expected="MOOT",
         summary="A person walks the release checklist in staging before each production release."),
    dict(id="D19", title="Run the data pipeline hourly, not continuously", decided_on="2025-08-01", owner="lena",
         systems=["data-pipeline"], premises=["p_warehouse_cost"], expected="MOOT",
         summary="The pipeline batches events and runs once an hour."),
    dict(id="D20", title="Pin the mobile app to React Native 0.72", decided_on="2025-09-01", owner="sofia",
         systems=["mobile-app"], premises=["p_rn_sdk"], expected="MOOT",
         summary="The mobile app stays on React Native 0.72 and the old architecture."),
    dict(id="D21", title="Self-host the status page", decided_on="2024-12-10", owner="marcus",
         systems=["infra"], premises=[], expected="UNDOCUMENTED",
         summary="The public status page runs on our own infrastructure."),
    dict(id="D22", title="Review access grants every month", decided_on="2025-04-01", owner="jonah",
         systems=["auth"], premises=["p_soc2_rotation"], expected="HOLDS",
         summary="A monthly review removes stale access to production systems."),
    dict(id="D23", title="Use UUIDv4 for every primary key", decided_on="2024-06-15", owner="priya",
         systems=["infra"], premises=["p_sharding"], expected="DISPUTED",
         summary="Tables use UUIDv4 primary keys instead of serial integers."),
    dict(id="D24", title="One-week on-call shifts", decided_on="2025-01-10", owner="marcus",
         systems=["infra"], premises=["p_oncall_pool"], expected="HOLDS",
         summary="On-call rotates weekly among the trained engineers."),
    dict(id="D25", title="Disable public sign-ups", decided_on="2025-10-01", owner="tomi",
         systems=["web-app"], premises=["p_signup_abuse"], expected="MOOT",
         summary="New accounts are created only through sales; the public sign-up form is off."),
    dict(id="D26", title="Retain logs for 30 days", decided_on="2024-08-01", owner="marcus",
         systems=["infra"], premises=["p_log_cost"], expected="HOLDS",
         summary="Application logs are deleted after 30 days."),
    dict(id="D27", title="Manage all infrastructure with Terraform", decided_on="2024-07-01", owner="marcus",
         systems=["infra"], premises=["p_iac_soc2"], expected="HOLDS",
         summary="No cloud resource is created by hand; everything goes through Terraform."),
    dict(id="D28", title="Deploy to a single region in Virginia", decided_on="2024-06-10", owner="tomi",
         systems=["infra"], premises=[], expected="RETIRED",
         summary="One AWS region, us-east-1, serves every customer."),
    dict(id="D29", title="Support customers by email only", decided_on="2024-09-15", owner="tomi",
         systems=["web-app"], premises=[], expected="UNDOCUMENTED",
         summary="Customer support runs through a shared inbox; no chat widget, no phone."),
    dict(id="D30", title="Block third-party cookies in the embed widget", decided_on="2025-11-05", owner="sofia",
         systems=["web-app"], premises=["p_chrome_3p"], expected="MOOT",
         summary="The embeddable widget uses first-party storage only."),
]

# Dated evidence that touches a premise. kind: pr | ticket | chat | doc
# rel: SUPPORTS | CONTRADICTS. Each item becomes one document in the corpus.
EVIDENCE = [
    dict(id="PR-412", kind="pr", date="2026-03-02", author="marcus", rel="CONTRADICTS", premise="p_gateway_limit",
         title="Raise the API gateway body limit to 100 MB",
         text="Upgrades Envoy to 1.31 and raises the request body limit on the gateway from 10 MB to 100 MB. "
              "Load-tested with 95 MB payloads; p99 latency unchanged. The old 10 MB limit was a default we never revisited."),
    dict(id="SRCH-233", kind="ticket", date="2025-09-14", author="lena", rel="CONTRADICTS", premise="p_es_incremental",
         title="Incremental indexing enabled after mapping migration",
         text="The new mapping with explicit nested fields accepts partial document updates. Incremental indexing is on in staging and the "
              "nightly full rebuild is no longer needed there."),
    dict(id="chat-2025-10-02-search", kind="chat", date="2025-10-02", author="lena", rel="SUPPORTS", premise="p_es_incremental",
         title="#search: rolling back incremental indexing",
         text="Rolled incremental indexing back in production. Update storms during bulk imports pushed indexing lag past 40 minutes. "
              "Until the mapping is reworked again the index still cannot take incremental updates at our volume, so the nightly rebuild stays."),
    dict(id="doc-soc2-2026", kind="doc", date="2026-01-28", author="jonah", rel="SUPPORTS", premise="p_soc2_rotation",
         title="SOC 2 Type II report, control CC6.1",
         text="The auditor confirmed the 90-day rotation control for all credentials and noted no exceptions. The requirement is unchanged for the 2026 period."),
    dict(id="PR-350", kind="pr", date="2025-11-18", author="marcus", rel="CONTRADICTS", premise="p_no_rollback",
         title="Automated rollback with reversible migrations",
         text="Every deploy now ships with a reversible migration and a one-command rollback. Rollback was exercised in production twice this week; "
              "no manual database restore is needed any more."),
    dict(id="doc-allhands-2026-04", kind="doc", date="2026-04-03", author="kwame", rel="CONTRADICTS", premise="p_team_size",
         title="All-hands notes, April 2026",
         text="Engineering headcount is 31 after the platform and data hires closed. Two more offers are out."),
    dict(id="SALES-91", kind="ticket", date="2026-02-20", author="tomi", rel="CONTRADICTS", premise="p_eu_customers",
         title="First customers in Ireland and Portugal signed",
         text="Signed two Irish customers and one in Portugal this quarter. Both asked about latency from Frankfurt and data residency."),
    dict(id="doc-metrics-2026-06", kind="doc", date="2026-06-30", author="priya", rel="SUPPORTS", premise="p_sendgrid_free",
         title="Notifications volume report, June 2026",
         text="Transactional email averaged 84 messages a day in June, with a peak of 97. We remain inside the free tier."),
    dict(id="PR-201", kind="pr", date="2025-04-09", author="priya", rel="CONTRADICTS", premise="p_no_ci_tests",
         title="Add the CI test suite",
         text="Adds pytest and Jest suites to CI, 1,180 tests, running on every PR in about six minutes."),
    dict(id="chat-2025-08-21-ci", kind="chat", date="2025-08-21", author="tomi", rel="SUPPORTS", premise="p_no_ci_tests",
         title="#eng: CI tests switched off",
         text="I have disabled the CI test job for now. It has been red for two weeks because of the flaky integration tests and people are merging around it. "
              "Until someone owns the suite, CI is effectively running no tests again."),
    dict(id="doc-arch-2026-02", kind="doc", date="2026-02-14", author="marcus", rel="SUPPORTS", premise="p_stateless",
         title="Autoscaling review",
         text="Web tier scaled from 3 to 14 pods during the February launch with no session loss because nothing is held in process memory."),
    dict(id="doc-aws-cmk", kind="doc", date="2025-12-05", author="jonah", rel="CONTRADICTS", premise="p_rds_no_cmk",
         title="AWS announcement: RDS customer-managed keys in eu-central-1",
         text="Amazon RDS now supports customer-managed KMS keys for encryption at rest in eu-central-1 (Frankfurt). Existing instances can be migrated with a snapshot restore."),
    dict(id="BILL-77", kind="ticket", date="2026-01-12", author="tomi", rel="SUPPORTS", premise="p_stripe_multi",
         title="Multi-currency request parked",
         text="Stripe multi-currency remains off on our account. Finance wants to keep a single settlement currency until the EU entity exists."),
    dict(id="doc-analytics-2026-03", kind="doc", date="2026-03-31", author="sofia", rel="SUPPORTS", premise="p_safari_share",
         title="Browser share, Q1 2026",
         text="Safari 14 and older: 0.4% of sessions. Chrome 71%, Safari 15+ 18%, Firefox 6%, other 4.6%."),
    dict(id="doc-privacy-2026", kind="doc", date="2026-05-10", author="jonah", rel="SUPPORTS", premise="p_gdpr",
         title="Privacy review 2026",
         text="EU customers are 38% of ARR. GDPR obligations apply and the DPA template was refreshed."),
    dict(id="chat-2026-07-09-ld", kind="chat", date="2026-07-09", author="kwame", rel="CONTRADICTS", premise="p_ld_budget",
         title="#finance: LaunchDarkly invoice",
         text="The July LaunchDarkly invoice came in at $2,100 after the seat true-up. That is four times what we budgeted."),
    dict(id="chat-2026-08-15-ld", kind="chat", date="2026-08-15", author="kwame", rel="SUPPORTS", premise="p_ld_budget",
         title="#finance: LaunchDarkly renegotiated",
         text="Renegotiated LaunchDarkly to a startup plan at $450 a month for 12 months. Under budget again, for now."),
    dict(id="PR-520", kind="pr", date="2026-05-22", author="sofia", rel="CONTRADICTS", premise="p_no_e2e",
         title="Playwright end-to-end suite for checkout and onboarding",
         text="Adds 64 Playwright tests covering sign-in, onboarding, checkout and the billing portal. Runs against staging on every release candidate."),
    dict(id="DATA-140", kind="ticket", date="2026-04-30", author="lena", rel="CONTRADICTS", premise="p_bq_ondemand",
         title="Moved BigQuery to flat-rate slots",
         text="We are now on 100 flat-rate slots. Query cost no longer depends on bytes scanned or on how often jobs run."),
    dict(id="doc-vendor-rn", kind="doc", date="2026-02-11", author="sofia", rel="CONTRADICTS", premise="p_rn_sdk",
         title="Payments SDK 5.0 release notes",
         text="Version 5.0 of the payments SDK supports the React Native New Architecture (Fabric and TurboModules). The bridge-based 4.x line is deprecated."),
    dict(id="ADR-notes-sharding", kind="doc", date="2026-01-20", author="priya", rel="CONTRADICTS", premise="p_sharding",
         title="Citus evaluation closed",
         text="We will not shard Postgres by tenant. The Citus evaluation is closed; a single primary with read replicas covers projected load through 2027."),
    dict(id="chat-2026-03-18-sharding", kind="chat", date="2026-03-18", author="tomi", rel="SUPPORTS", premise="p_sharding",
         title="#eng: sharding back on the roadmap",
         text="After the enterprise deal, sharding by tenant is back on the Q4 roadmap. Treat it as planned again."),
    dict(id="doc-oncall-2026", kind="doc", date="2026-06-01", author="marcus", rel="SUPPORTS", premise="p_oncall_pool",
         title="On-call readiness, June 2026",
         text="Four engineers are fully trained for on-call. Two more are shadowing and should be ready by September."),
    dict(id="doc-abuse-2026-06", kind="doc", date="2026-06-12", author="jonah", rel="CONTRADICTS", premise="p_signup_abuse",
         title="Sign-up abuse review",
         text="Since the captcha and rate limits shipped in December there have been zero abusive sign-ups in six months. The bot wave is over."),
    dict(id="doc-logcost-2026", kind="doc", date="2026-02-01", author="marcus", rel="SUPPORTS", premise="p_log_cost",
         title="Observability cost review",
         text="Log storage is billed at $0.50 per GB a month. Retention beyond 30 days would double the bill."),
    dict(id="doc-soc2-iac", kind="doc", date="2026-01-28", author="jonah", rel="SUPPORTS", premise="p_iac_soc2",
         title="SOC 2 Type II report, control CC8.1",
         text="Change management control satisfied by infrastructure as code with peer review. The auditor sampled 25 changes, all through Terraform."),
    dict(id="doc-news-cookies", kind="doc", date="2025-07-22", author="sofia", rel="CONTRADICTS", premise="p_chrome_3p",
         title="Google drops plan to remove third-party cookies",
         text="Google announced it will not remove third-party cookies from Chrome and will not roll out a new standalone prompt either."),
]

# Distractor documents: realistic noise that touches no premise.
DISTRACTORS = [
    ("PR-398", "pr", "2026-01-15", "priya", "Fix timezone bug in invoice dates", "Invoices generated after 23:00 UTC showed the next day's date. Dates are now rendered in the customer's billing timezone."),
    ("PR-430", "pr", "2026-03-20", "sofia", "New onboarding checklist component", "Replaces the modal onboarding with an inline checklist. Completion rate in the A/B test went from 41% to 58%."),
    ("PR-455", "pr", "2026-04-08", "marcus", "Bump Kubernetes to 1.31", "Cluster upgrade with no API deprecations affecting our manifests."),
    ("PR-471", "pr", "2026-04-29", "lena", "Dedupe events by idempotency key", "Pipeline now drops duplicate events within a 24-hour window."),
    ("PR-488", "pr", "2026-05-13", "priya", "Rate-limit the export endpoint", "Exports are limited to 10 per hour per tenant after the incident on May 9."),
    ("PR-502", "pr", "2026-06-03", "jonah", "Add security headers", "CSP, HSTS and frame-ancestors headers added to all responses."),
    ("PR-515", "pr", "2026-06-24", "sofia", "Dark mode", "Adds a theme toggle and dark tokens."),
    ("PR-531", "pr", "2026-07-15", "marcus", "Spot instances for batch workers", "Batch workers run on spot capacity with checkpointing; saves about 60% on that pool."),
    ("OPS-301", "ticket", "2026-02-09", "marcus", "Disk alert on the metrics node", "Prometheus retention reduced from 30 to 15 days after disk hit 92%."),
    ("OPS-318", "ticket", "2026-05-09", "marcus", "Incident: export endpoint saturated workers", "A tenant triggered 400 exports in ten minutes. Mitigated by scaling workers; follow-up is rate limiting."),
    ("BILL-80", "ticket", "2026-03-03", "tomi", "Annual invoicing for enterprise", "Enterprise customers can be billed annually in advance."),
    ("AUTH-120", "ticket", "2026-04-14", "jonah", "SSO for Okta customers", "SAML SSO shipped for three Okta customers."),
    ("DATA-150", "ticket", "2026-06-20", "lena", "Late-arriving events", "Events arriving more than 48 hours late are now routed to a quarantine table."),
    ("SRCH-240", "ticket", "2026-01-30", "lena", "Synonyms for product names", "Added a synonym list so searches for old product names still match."),
    ("MOB-77", "ticket", "2026-03-11", "sofia", "Crash on Android 14 camera permission", "Fixed a crash when the camera permission was denied twice."),
    ("chat-2026-01-08-standup", "chat", "2026-01-08", "kwame", "#eng: standup notes", "Priya on invoices, Sofia on onboarding, Marcus on the k8s upgrade. Lena out until Monday."),
    ("chat-2026-02-26-hiring", "chat", "2026-02-26", "kwame", "#eng: hiring", "Two platform offers accepted, starting in March. Data engineer loop continues."),
    ("chat-2026-04-22-launch", "chat", "2026-04-22", "tomi", "#general: launch", "Reporting v2 is live. Thanks everyone. Watch the dashboards tonight."),
    ("chat-2026-05-16-farewell", "chat", "2026-05-16", "tomi", "#general: farewell", "Ada's last day was yesterday. Platform decisions she owned need new owners; Kwame is collecting the list."),
    ("chat-2026-06-05-retro", "chat", "2026-06-05", "kwame", "#eng: retro", "Retro themes: too many Slack decisions never reach an ADR; nobody knows which rules are still real."),
    ("chat-2026-07-30-oncall", "chat", "2026-07-30", "marcus", "#ops: quiet week", "Zero pages this week. Shadowing is going well."),
    ("chat-2026-08-27-perf", "chat", "2026-08-27", "priya", "#backend: perf", "Invoice generation is 3x faster after the query rewrite."),
    ("chat-2026-09-10-roadmap", "chat", "2026-09-10", "tomi", "#general: Q4 roadmap", "Q4 priorities: enterprise SSO rollout, reporting exports, mobile refresh."),
    ("doc-handbook-deploys", "doc", "2025-06-01", "marcus", "Engineering handbook: how we deploy", "Deploys go through the pipeline; a canary takes 10% of traffic for 15 minutes before full rollout."),
    ("doc-handbook-reviews", "doc", "2025-06-01", "tomi", "Engineering handbook: code review", "Reviews should be returned within one working day. Nits are prefixed with 'nit:'."),
    ("doc-okr-2026-h2", "doc", "2026-07-01", "tomi", "H2 2026 OKRs", "Objective: enterprise ready. Key results: SSO for all enterprise tenants, 99.95% availability, SOC 2 renewed."),
    ("doc-postmortem-may", "doc", "2026-05-12", "marcus", "Postmortem: export saturation", "Root cause: unbounded exports per tenant. Action items: rate limit, worker autoscaling, alerting on queue depth."),
    ("doc-vendor-review", "doc", "2026-03-15", "kwame", "Vendor review Q1", "Reviewed Datadog, LaunchDarkly, SendGrid and Vercel contracts. No changes this quarter."),
    ("doc-design-system", "doc", "2026-02-20", "sofia", "Design system v2", "Tokens, spacing and components documented; dark theme planned."),
    ("doc-dr-plan", "doc", "2026-01-10", "marcus", "Disaster recovery plan", "RPO 1 hour, RTO 4 hours, tested quarterly."),
]

AS_OF = "2026-10-16"


def noise_documents(n: int = 150, seed: int = 7) -> list[tuple]:
    """Templated background noise so retrieval is not trivially easy: realistic PRs, tickets and
    chat about the same systems and vocabulary, touching no premise. Deterministic for a seed."""
    import random
    r = random.Random(seed)
    systems = ["uploads API", "API gateway", "billing", "auth", "search", "data pipeline", "web app", "mobile app", "notifications", "infrastructure"]
    verbs = ["Refactor", "Fix", "Tune", "Document", "Instrument", "Migrate", "Speed up", "Clean up", "Harden", "Retry"]
    objs = ["upload retries", "gateway timeouts", "invoice PDF rendering", "session cookie flags", "index warmup", "pipeline backfill",
            "onboarding copy", "photo picker", "email templates", "Terraform modules", "rate limits", "CSV parser", "deploy script",
            "rollback notes", "feature flag cleanup", "Safari layout bug", "log sampling", "on-call runbook", "SOC 2 evidence folder",
            "BigQuery views", "Redis eviction policy", "Stripe webhook retries", "status page copy", "LaunchDarkly SDK bump",
            "Playwright flake", "SendGrid templates", "Envoy config lint", "Postgres vacuum schedule", "UUID formatting", "EU latency dashboard"]
    tails = ["No behaviour change.", "Covered by existing tests.", "Follow-up to last week's incident review.", "Requested by support.",
             "Part of the Q3 cleanup.", "Rolled out behind a flag.", "Measured on staging first.", "Docs updated.", "Nothing user-facing.", "Small, reviewed in person."]
    people = [p[0] for p in PEOPLE]
    out = []
    for i in range(n):
        kind = r.choice(["pr", "pr", "ticket", "chat", "doc"])
        sysname = r.choice(systems); verb = r.choice(verbs); obj = r.choice(objs)
        month = r.randint(1, 10); day = r.randint(1, 28); year = r.choice([2025, 2025, 2026])
        date = f"{year}-{month:02d}-{day:02d}"
        author = r.choice(people)
        title = f"{verb} {obj}" if kind != "chat" else f"#{sysname.split()[0].lower()}: {obj}"
        text = f"{verb} the {obj} in the {sysname}. {r.choice(tails)} {r.choice(tails)}"
        prefix = {"pr": "PR-", "ticket": "OPS-", "chat": "chat-noise-", "doc": "doc-note-"}[kind]
        out.append((f"{prefix}{900 + i}", kind, date, author, title, text))
    return out
