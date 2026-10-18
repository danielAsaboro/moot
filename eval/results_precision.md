# Precision of flags on real history (study P1)

Every flag a method raised on one of the backtest's 97 tool decisions while its repository still listed it in force, up to 2023-10-17 (so each has three full years of future). Graded by one rule fixed before this ran (docs/studies.md P1, the H1 rule): confirmed if within three years the repository changed the ADR's status, archived it, titled a later ADR as dropping its tool, or the tool left its dependency manifests or Terraform. Nobody on this project graded a flag.

| method | flags | confirmed | precision (95% CI) | flags per confirmed death | median lead to the repository's own change |
|---|---|---|---|---|---|
| **Moot gate (DENY)** | 12 | 1 | 0.08 (0.01–0.35) | 12.0 | 350 days |
| age ≥ 3 years | 45 | 3 | 0.07 (0.02–0.18) | 15.0 | 329 days |
| trust the ADR | 0 | 0 | – | – | – |
| random, Moot's budget (mean of 200) | 10.5 | 1.4 | 0.13 | – | – |

## Every Moot flag and what the repository did

| decision | flagged | confirmed | what happened, and when |
|---|---|---|---|
| CMSgov/easi-app:0002-use-terraform.md | 2023-09-01 | no |  |
| CMSgov/easi-app:0017-go-orm.md | 2023-05-01 | no |  |
| alphagov/govuk-aws:0012-security-groups-in-terraform.md | 2023-09-01 | no |  |
| alphagov/govuk-aws:0028-combine-api-mongo-cluster-into-mongo-cluster.md | 2018-11-01 | yes | replaced: 38. Mongo Replacement by DocumentDB (2019-10-17) |
| alphagov/govuk-infrastructure:0007-use-fluentbit-elasticsearch-and-kibana-for-application-logs.md | 2021-08-16 | no |  |
| edgexfoundry/edgex-docs:0017-consul-security.md | 2023-09-01 | no |  |
| kyma-project/community:dr-006-Kubeless_as_the_Faas_solution.md | 2023-01-01 | no |  |
| ministryofjustice/cloud-platform:001-Use-AWS-hosted-elasticsearch.md | 2021-02-01 | no |  |
| ministryofjustice/cloud-platform:016-Kibana-is-open-to-all-service-teams.md | 2021-02-01 | no |  |
| openedx/edx-platform:0003-permissions-via-bridgekeeper.rst | 2022-11-01 | no |  |
| openedx/edx-platform:permissions.rst | 2021-02-01 | no |  |
| thomvaill/log4brains:20201103-use-lunr-for-search.md | 2021-09-01 | no |  |
