# Stated reasons: before and after reading ADR text

Four public repositories ingested with `moot ingest-github`, each built twice on 2026-10-19: first from titles, status lines and history alone (the connector before this change), then with the reasons each ADR states in its own Context, Decision and Consequences, read by a model and kept only as literal quoted spans (`moot/connectors/reasons.py`). Same day, same tool checks, same verdict rules. Model replies are cached in `data/github/<repo>/reasons.json`, so the after column re-derives without a model.

## Verdicts

| graph | HOLDS | MOOT | DISPUTED | UNDOCUMENTED | RETIRED |
|---|---|---|---|---|---|
| npryce/adr-tools before | 0 | 0 | 0 | 9 | 0 |
| **npryce/adr-tools after** | 7 | 0 | 0 | 2 | 0 |
| thomvaill/log4brains before | 3 | 1 | 0 | 5 | 2 |
| **thomvaill/log4brains after** | 6 | 2 | 0 | 1 | 2 |
| alphagov/govuk-infrastructure before | 8 | 4 | 0 | 11 | 1 |
| **alphagov/govuk-infrastructure after** | 12 | 6 | 0 | 5 | 1 |
| alphagov/govuk-aws before | 5 | 3 | 0 | 21 | 2 |
| **alphagov/govuk-aws after** | 10 | 9 | 0 | 10 | 2 |
| all four, before | 16 | 8 | 0 | 46 | 5 |
| **all four, after** | 35 | 17 | 0 | 18 | 5 |

## What an agent may do (the gate, depth 6)

| graph | ALLOW | REVALIDATE | DENY |
|---|---|---|---|
| npryce/adr-tools before | 0 | 9 | 0 |
| npryce/adr-tools after | 0 | 9 | 0 |
| thomvaill/log4brains before | 3 | 5 | 3 |
| thomvaill/log4brains after | 0 | 7 | 4 |
| alphagov/govuk-infrastructure before | 4 | 15 | 5 |
| alphagov/govuk-infrastructure after | 2 | 15 | 7 |
| alphagov/govuk-aws before | 1 | 25 | 5 |
| alphagov/govuk-aws after | 0 | 20 | 11 |
| **all four, after** | 2 | 51 | 22 |

## What the model read and what the validator kept

- ADRs read: 75 of 75 decisions (0 not read). Reasons kept: 157; dropped by the validator: 6 (quote not a literal span, in the title or Status, too short, a repeat, or a tool link that names no catalogue tool in its quote).
- Reasons linked to a checked tool (DERIVED_FROM its maintained / open source / no-known-vulnerability premises): 31.
- Later ADRs judged against earlier reasons: 8 dated SUPPORTS or CONTRADICTS edges kept, 0 dropped.
- Decisions still without a stated reason (not retired): 24.

## Read this before the numbers

- **Most new HOLDS are not checked.** Of 35 HOLDS after extraction, 2 pass the gate (ALLOW); 33 rest on at least one stated reason nobody has evidence for either way, so the gate answers REVALIDATE. Moving a decision from UNDOCUMENTED to HOLDS means *the ADR says why, and nothing on record contradicts it*, not *we confirmed it*.
- **The verdict rules did not change.** An unevidenced reason does not change a verdict (as in Larkspur); the change is that the graph now records what the ADR says, with the quote, character span, section, document and model on every Premise.
- **A model can miss or misread a reason.** The span check stops invented quotes, not a wrong reading of a real one. Every reason in the graph links back to its sentence, so a reader can check it in one click.
- **One local model, one run** (temperature 0, seed 7). A different model would keep different reasons.

## Verdicts that changed

| graph | decision | before | after | gate before | gate after |
|---|---|---|---|---|---|
| gh_npryce_adr_tools | 0001-record-architecture-decisions: 1. Record architecture decisions | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_npryce_adr_tools | 0003-single-command-with-subcommands: 3. Single command with subcommands | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_npryce_adr_tools | 0004-markdown-format: 4. Markdown format | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_npryce_adr_tools | 0005-help-comments: 5. Help comments | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_npryce_adr_tools | 0006-packaging-and-distribution-in-other-version-control-repositories: 6. Packaging and distribution in other version control repositories | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_npryce_adr_tools | 0008-use-iso-8601-format-for-dates: 8. Use ISO 8601 Format for Dates | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_npryce_adr_tools | 0009-help-scripts: 9. Help scripts | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_thomvaill_log4brains | 20200924-use-markdown-architectural-decision-records: Use Markdown Architectural Decision Records | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_thomvaill_log4brains | 20200925-multi-packages-architecture-in-a-monorepo-with-yarn-and-lerna: Multi-packages architecture in a monorepo with Yarn and Lerna | HOLDS | MOOT | ALLOW | DENY |
| gh_thomvaill_log4brains | 20200925-use-prettier-eslint-airbnb-for-the-code-style: Use Prettier-ESLint Airbnb for the code style | HOLDS | HOLDS | ALLOW | REVALIDATE |
| gh_thomvaill_log4brains | 20201016-use-the-adr-slug-as-its-unique-id: Use the ADR slug as its unique ID | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_thomvaill_log4brains | 20201026-the-core-api-is-responsible-for-enhancing-the-adr-markdown-body-with-mdx: The core API is responsible for enhancing the ADR markdown body with M | HOLDS | HOLDS | ALLOW | REVALIDATE |
| gh_thomvaill_log4brains | 20210113-distribute-log4brains-as-a-global-npm-package: Distribute Log4brains as a global NPM package | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_thomvaill_log4brains | 20241217-switch-back-to-github-flow: Switch back to GitHub Flow, but keeping the automated beta releases | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_alphagov_govuk_infrastructure | 0001-record-architecture-decisions: 1. Record architecture decisions | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_alphagov_govuk_infrastructure | 0003-split-terraform-state-into-separate-aws-cluster-and-kubernetes-resource-phases: 3. Split Terraform state into separate AWS cluster and Kubernetes reso | UNDOCUMENTED | MOOT | REVALIDATE | DENY |
| gh_alphagov_govuk_infrastructure | 0006-use-helm-for-application-package-management: 6. Use Helm for application package management | HOLDS | HOLDS | ALLOW | REVALIDATE |
| gh_alphagov_govuk_infrastructure | 0012-non-govuk-domain-policy: 12. Non-GOV.UK domain policy | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_alphagov_govuk_infrastructure | 0014-replace-terraform-cloud: 14. Replace Terraform Cloud backend with AWS S3 | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_alphagov_govuk_infrastructure | 0015-maintain-a-readonly-role: 15. Maintain a read-only IAM role | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_alphagov_govuk_infrastructure | 0016-use-iam-roles-for-services: 16. Use IAM roles for external services and applications | UNDOCUMENTED | MOOT | REVALIDATE | DENY |
| gh_alphagov_govuk_infrastructure | 0023-use-opa-gatekeeper: 23. Use OPA Gatekeeper | HOLDS | HOLDS | ALLOW | REVALIDATE |
| gh_alphagov_govuk_aws | 0001-record-architecture-decisions: 1. Record architecture decisions | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_alphagov_govuk_aws | 0010-terraform-directory-structure: 10. Terraform directory structure | UNDOCUMENTED | MOOT | REVALIDATE | DENY |
| gh_alphagov_govuk_aws | 0011-migration-strategy: 11. Migration Strategy | UNDOCUMENTED | MOOT | REVALIDATE | DENY |
| gh_alphagov_govuk_aws | 0014-launch-config-change-propagation-process: 14. Launch Config change propagation process | UNDOCUMENTED | MOOT | REVALIDATE | DENY |
| gh_alphagov_govuk_aws | 0016-internal-dns-zones: 16. internal DNS zones | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_alphagov_govuk_aws | 0019-centralise-mysql-databases: 19. Centralise MySQL Databases | UNDOCUMENTED | MOOT | REVALIDATE | DENY |
| gh_alphagov_govuk_aws | 0020-merge-api-postgresql-instance-into-main-postgresql-instance: 20. Merge API PostgreSQL instance into main PostgreSQL instance | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_alphagov_govuk_aws | 0022-remove-the-elasticsearch-proxy: 22. Remove the Elasticsearch proxy | HOLDS | HOLDS | ALLOW | REVALIDATE |
| gh_alphagov_govuk_aws | 0024-ami-lookups: 24. AMI Lookups | UNDOCUMENTED | MOOT | REVALIDATE | DENY |
| gh_alphagov_govuk_aws | 0026-remove-load-balancer-tier: 26. Remove load balancer tier | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |
| gh_alphagov_govuk_aws | 0037-alb-health-checks: 37. ALB Health Checks | UNDOCUMENTED | MOOT | REVALIDATE | DENY |
| gh_alphagov_govuk_aws | 0039-non-govuk-domain-policy: 39. Non-GOV.UK domain policy | UNDOCUMENTED | HOLDS | REVALIDATE | REVALIDATE |

## Why each new MOOT is moot

A decision turns MOOT only through a dated contradiction: a tool check (GitHub, OSV, licence) on a tool a stated reason depends on, or a later ADR's exact words. Check each one; this is where a misread reason would show.

| graph | decision | reason | contradicted by | on | quote |
|---|---|---|---|---|---|
| gh_thomvaill_log4brains | 20200925-multi-packages-architecture-in-a-monorepo-with-yarn-and-lerna | Yarn and Lerna are considered a good practice used by many open-source projects for publis | src:20241217-switch-back-to-github-flow | 2024-12-17 | Lerna**, which we use for managing our monorepo, does not integrate well with Git Flow processes |
| gh_alphagov_govuk_infrastructure | 0003-split-terraform-state-into-separate-aws-cluster-and-kubernetes-resource-phases | Terraform is open source | open_source:terraform | 2026-10-19 | source-available: BUSL-1.1 |
| gh_alphagov_govuk_infrastructure | 0016-use-iam-roles-for-services | The current release of Kubernetes has no known vulnerability | no_known_vuln:kubernetes | 2026-10-19 | 2 OSV advisories affect v1.37.1 |
| gh_alphagov_govuk_aws | 0010-terraform-directory-structure | Terraform is open source | open_source:terraform | 2026-10-19 | source-available: BUSL-1.1 |
| gh_alphagov_govuk_aws | 0011-migration-strategy | Puppet is actively maintained | maintained:puppet | 2026-10-19 | last commit to main on 2024-12-11 |
| gh_alphagov_govuk_aws | 0014-launch-config-change-propagation-process | Terraform is open source | open_source:terraform | 2026-10-19 | source-available: BUSL-1.1 |
| gh_alphagov_govuk_aws | 0019-centralise-mysql-databases | Puppet is actively maintained | maintained:puppet | 2026-10-19 | last commit to main on 2024-12-11 |
| gh_alphagov_govuk_aws | 0024-ami-lookups | Puppet is actively maintained | maintained:puppet | 2026-10-19 | last commit to main on 2024-12-11 |
| gh_alphagov_govuk_aws | 0037-alb-health-checks | Puppet is actively maintained | maintained:puppet | 2026-10-19 | last commit to main on 2024-12-11 |
