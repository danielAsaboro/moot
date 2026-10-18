# Held-out: does this real decision still hold? (study H1)

Every arm sees only what existed on **2023-10-17** and answers HOLDS or DEAD for each decision. The repositories grade it: a decision is DEAD if, by 2026-10-17, its own repository marked it superseded or deprecated, a later ADR dropped its tool, or the tool left the repository's dependency manifests or Terraform; HOLDS otherwise. Nobody on this project labelled a unit. The gold was hashed before any arm ran (`a6001e20aaa644ca…`, eval/heldout/GOLD.sha256) and the scorer refuses to run if it changes. Prompts were fixed on the dev split; the test split ran once.

## Test split: 64 decisions, 5 DEAD

Accuracy is the primary metric. DEAD caught, false alarms, precision and balanced accuracy were registered too (docs/studies.md H1); the false-alarm column was added to the table after the first test numbers were seen. Nothing about the gold, the labels or Moot's rules changed after any test number was seen.

| arm | right | accuracy (95% CI) | DEAD caught (recall) | false alarms (HOLDS called DEAD) | precision of DEAD calls | balanced accuracy | vs Moot (only Moot right / only it right, exact McNemar p) |
|---|---|---|---|---|---|---|---|
| **Moot gate (FalkorDB)** | 52/64 | 0.81 (0.70–0.89) | 1/5 | 8/59 | 1/9 (0.11) | 0.53 | – |
| Moot rules, FalkorDB removed (BM25 top 3) | 24/64 | 0.38 (0.27–0.50) | 2/5 | 37/59 | 2/39 (0.05) | 0.39 | 30 / 2, p = 0.000 |
| majority class | 59/64 | 0.92 (0.83–0.97) | 0/5 | 0/59 | no DEAD calls | 0.50 | 1 / 8, p = 0.039 |
| age ≥ 3 years | 28/64 | 0.44 (0.32–0.56) | 3/5 | 34/59 | 3/37 (0.08) | 0.51 | 28 / 4, p = 0.000 |
| trust the ADR's status | 59/64 | 0.92 (0.83–0.97) | 0/5 | 0/59 | no DEAD calls | 0.50 | 1 / 8, p = 0.039 |
| BM25 RAG + qwen3.8:27b | 57/64 | 0.89 (0.79–0.95) | 2/5 | 4/59 | 2/6 (0.33) | 0.67 | 4 / 9, p = 0.267 |
| LLM agent with GitHub/OSV tools (openai/gpt-oss-20b) | 55/64 | 0.86 (0.75–0.92) | 1/5 | 5/59 | 1/6 (0.17) | 0.56 | 2 / 5, p = 0.453 |

**Post hoc, added after the first test numbers were seen and justified on the dev split only** (4 of Moot's 5 dev false alarms were licence changes: Terraform, Consul, Elasticsearch, Kibana). It applies the rule Moot already uses for ingested repositories (licence checks are advisory unless a stated reason depends on them; commit ac86bea, written before this study's gold) to the same graph. It does not replace the frozen row above.

| arm | right | accuracy (95% CI) | DEAD caught (recall) | false alarms (HOLDS called DEAD) | precision of DEAD calls | balanced accuracy | vs Moot (only Moot right / only it right, exact McNemar p) |
|---|---|---|---|---|---|---|---|
| Moot gate, licence checks advisory (post hoc) | 56/64 | 0.88 (0.77–0.94) | 0/5 | 3/59 | 0/3 (0.00) | 0.47 | 1 / 5, p = 0.219 |

Agent cost on the test split: 60,247 tokens in, 4,491 out, $0.0059, 109 tool calls, median 1506 ms of model time per decision. BM25 RAG: median 39.9 s per decision on a local model. Moot, its FalkorDB-removed ablation and the rule baselines make no model call.

## What an agent would have been allowed to do (study A1, test split)

An agent asks before acting on each decision on T0. Moot's gate allows only on ALLOW (DENY and REVALIDATE block); the model arms allow on HOLDS; trust the ADR allows everything; the age rule blocks at three years. The two columns pull against each other and are never summed.

| gatekeeper | actions on decisions that later died, allowed | actions on decisions that held, blocked |
|---|---|---|
| **Moot gate (FalkorDB)** | 0/5 (0.00–0.43) | 59/59 (0.94–1.00) |
| Moot gate, warn policy (post hoc: the product default since 2026-10-21) | 4/5 (0.38–0.96) | 8/59 (0.07–0.25) |
| trust the ADR's status | 5/5 (0.57–1.00) | 0/59 (0.00–0.06) |
| age ≥ 3 years | 2/5 (0.12–0.77) | 34/59 (0.45–0.69) |
| BM25 RAG + qwen3.8:27b | 3/5 (0.23–0.88) | 4/59 (0.03–0.16) |
| LLM agent with GitHub/OSV tools (openai/gpt-oss-20b) | 4/5 (0.38–0.96) | 5/59 (0.04–0.18) |

Added after these numbers were seen: of the 59 held decisions Moot's gate blocked, 31 had an ADR author still committing to the repository in the year before T0, someone a blocked agent could have asked (`moot/heldout/route.py`, from git history). The rest had nobody on record still active.

## Dev split (28 decisions, 2 DEAD), used to fix the prompts

| arm | right | DEAD caught | false alarms | DEAD calls |
|---|---|---|---|---|
| **Moot gate (FalkorDB)** | 21/28 | 0/2 | 5/26 | 5 |
| Moot rules, FalkorDB removed (BM25 top 3) | 12/28 | 2/2 | 16/26 | 18 |
| majority class | 26/28 | 0/2 | 0/26 | 0 |
| age ≥ 3 years | 11/28 | 0/2 | 15/26 | 15 |
| trust the ADR's status | 26/28 | 0/2 | 0/26 | 0 |
| BM25 RAG + qwen3.8:27b | 24/28 | 0/2 | 2/26 | 2 |
| LLM agent with GitHub/OSV tools (openai/gpt-oss-20b) | 24/28 | 0/2 | 2/26 | 2 |

## Every test decision

| decision | gold | backed by | Moot | Moot's reason | RAG | agent | age |
|---|---|---|---|---|---|---|---|
| CMSgov/easi-app:0002-use-terraform.md | HOLDS | status | DEAD | "Terraform is open source" was contradicted on 2023-08-10 by open_source:terraform:2023-08-10. | HOLDS | HOLDS | DEAD |
| CMSgov/easi-app:0012-backend-testing-suite.md | HOLDS | code | HOLDS | "Testify is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| CMSgov/easi-app:0014-use-mux-for-routing.md | HOLDS | code | HOLDS | "gorilla/mux is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| CMSgov/easi-app:0016-migration-tool.md | HOLDS | status | HOLDS | "Flyway is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| CMSgov/easi-app:0017-go-orm.md | HOLDS | code | DEAD | "sqlx is actively maintained" was contradicted on 2023-04-16 by maintained:sqlx:2023-04-16. | HOLDS | DEAD | DEAD |
| DFE-Digital/apply-for-teacher-training:0002-use-devise-for-authentication.md | HOLDS | code | HOLDS | "Devise is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| DFE-Digital/find-a-lost-trn:00003-use-rails.md | HOLDS | code | HOLDS | "Ruby on Rails is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| DFE-Digital/find-a-lost-trn:00004-use-postgres-state.md | HOLDS | code | HOLDS | "PostgreSQL is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| DFE-Digital/find-a-lost-trn:00006-sidekiq-and-redis.md | HOLDS | code | HOLDS | "Redis is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| HHS/Head-Start-TTADP:0007-use-plantuml-for-diagrams.md | HOLDS | code | HOLDS | "PlantUML is actively maintained" was contradicted by maintained:plantuml:2012-09-07 and re-affirmed by mainta | HOLDS | HOLDS | DEAD |
| SmartBear/git-en-boite:0009-prefer-dugite-over-raw-git-commands-in-tests.md | HOLDS | code | HOLDS | "dugite is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| alphagov/govuk-aws:0007-puppet-cert-management.md | HOLDS | status | HOLDS | "Puppet is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| alphagov/govuk-aws:0008-postgres-on-puppetmaster.md | HOLDS | status | HOLDS | "Puppet is open source" has no dated evidence either way; nobody has checked it. | DEAD | DEAD | DEAD |
| alphagov/govuk-aws:0025-use-elasticache-for-redis.md | HOLDS | code | HOLDS | "Redis is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| alphagov/govuk-aws:0029-combine-api-redis-into-backend-redis.md | HOLDS | code | HOLDS | "Redis is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| alphagov/govuk-infrastructure:0002-use-aws-eks-terraform-module.md | HOLDS | code | HOLDS | "terraform-aws-eks module is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| alphagov/govuk-infrastructure:0004-use-aws-load-balancer-controller-for-edge-traffic-services.md | HOLDS | code | HOLDS | "AWS Load Balancer Controller is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| alphagov/govuk-infrastructure:0005-use-eks-managed-node-groups.md | HOLDS | status | HOLDS | "Kubernetes is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| alphagov/govuk-infrastructure:0006-use-helm-for-application-package-management.md | HOLDS | code | HOLDS | "Helm is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| alphagov/govuk-infrastructure:0007-use-fluentbit-elasticsearch-and-kibana-for-application-logs.md | DEAD | status | DEAD | "Elasticsearch is open source" was contradicted on 2021-01-14 by open_source:elasticsearch:2021-01-14. | HOLDS | DEAD | HOLDS |
| alphagov/govuk-infrastructure:0008-use-external-secrets-for-secrets-storage.md | HOLDS | code | HOLDS | "external-secrets is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| alphagov/govuk-infrastructure:0009-use-external-dns-for-dns-record-management.md | HOLDS | code | HOLDS | "external-dns is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| apache/james-project:0019-reactor-netty-adoption.md | HOLDS | code | HOLDS | "Reactor Netty is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| apache/james-project:0033-use-scala-in-event-sourcing-modules.md | HOLDS | code | HOLDS | "Scala is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| apache/james-project:0052-pulsar-mailqueue.md | HOLDS | code | HOLDS | "Apache Pulsar is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| apache/james-project:0056-opensearch-migration.md | HOLDS | status | HOLDS | "OpenSearch is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| apache/james-project:0059-upgrade-to-cassadra-driver-4.md | HOLDS | code | HOLDS | "Cassandra Java driver is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| backstage/backstage:adr012-use-luxon-locale-and-date-presets.md | HOLDS | code | HOLDS | "Luxon is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| change-metrics/monocle:0002-Choice-of-Elasticsearch.md | HOLDS | status | DEAD | "Elasticsearch is open source" was contradicted on 2021-01-14 by open_source:elasticsearch:2021-01-14. | HOLDS | DEAD | DEAD |
| change-metrics/monocle:0003-Choice-of-React.md | HOLDS | code | HOLDS | "React is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| cljdoc/cljdoc:0010-use-terraform-to-create-document-infrastructure.md | HOLDS | code | DEAD | "Terraform is open source" was contradicted on 2023-08-10 by open_source:terraform:2023-08-10. | HOLDS | HOLDS | DEAD |
| cljdoc/cljdoc:0017-use-nomad-for-deployment.md | HOLDS | status | DEAD | "Nomad is open source" was contradicted on 2023-08-10 by open_source:nomad:2023-08-10. | HOLDS | HOLDS | DEAD |
| cloudfoundry/korifi:0007-use-contour-for-ingress.md | HOLDS | status | HOLDS | "Contour is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| guardian/dotcom-rendering:use-percy-for-e2e-visual-regression-testing.md | DEAD | code | HOLDS | "Cypress is open source" has no dated evidence either way; nobody has checked it. | DEAD | HOLDS | HOLDS |
| kyma-project/community:dr-005-Istio_as_the_API_Gateway.md | HOLDS | status | HOLDS | "Istio is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| ministryofjustice/cloud-platform:001-Use-AWS-hosted-elasticsearch.md | HOLDS | status | DEAD | "Elasticsearch is open source" was contradicted on 2021-01-14 by open_source:elasticsearch:2021-01-14. | DEAD | HOLDS | DEAD |
| ministryofjustice/cloud-platform:003-Use-Concourse-CI.md | HOLDS | status | HOLDS | "Concourse CI is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| ministryofjustice/cloud-platform:004-use-kubernetes-for-container-management.md | HOLDS | status | HOLDS | "Kubernetes is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| ministryofjustice/cloud-platform:011-Introduce-Open-Policy-Agent.md | HOLDS | status | HOLDS | "Open Policy Agent is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| ministryofjustice/cloud-platform:014-Why-we-build-our-own-kubernetes-cluster.md | HOLDS | status | HOLDS | "Kubernetes is open source" has no dated evidence either way; nobody has checked it. | DEAD | DEAD | DEAD |
| ministryofjustice/cloud-platform:022-EKS.md | HOLDS | status | HOLDS | "Kubernetes is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| ministryofjustice/modernisation-platform:0007-use-terratest-opa-and-go-for-testing.md | HOLDS | status | HOLDS | "Open Policy Agent is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| mozilla/fxa:0002-use-react-redux-and-typescript-for-subscription-management-pages.md | DEAD | code | HOLDS | "Redux is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| mozilla/fxa:0010-transition-fxa-from-backbone-to-react.md | HOLDS | code | HOLDS | "React is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| mozilla/fxa:0021-use-internjs-testing.md | DEAD | code | HOLDS | "Intern is open source" has no dated evidence either way; nobody has checked it. | DEAD | HOLDS | DEAD |
| mozilla/fxa:0035-refactor-payments-frontend-with-nextjs.md | HOLDS | code | HOLDS | "Next.js is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| mozilla/fxa:0037-use-nx-for-monorepo.md | HOLDS | code | HOLDS | "Nx is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| openedx/edx-enterprise:0012-enterprise-feature-flags-waffle.rst | HOLDS | code | HOLDS | "django-waffle is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| openedx/edx-platform:0002-waffle-utils-extraction.rst | HOLDS | code | HOLDS | "django-waffle is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| openedx/edx-platform:0003-permissions-via-bridgekeeper.rst | HOLDS | code | DEAD | "bridgekeeper is actively maintained" was contradicted on 2022-10-06 by maintained:bridgekeeper:2022-10-06. | HOLDS | DEAD | DEAD |
| openedx/edx-platform:0004-waffle-util-namespacing.rst | HOLDS | code | HOLDS | "django-waffle is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| openedx/edx-platform:permissions.rst | HOLDS | code | HOLDS | "django-rules is actively maintained" was contradicted by maintained:django-rules:2021-01-16 and re-affirmed b | DEAD | HOLDS | DEAD |
| openedx/frontend-app-learning:0006-thunk-and-api-naming.md | DEAD | code | HOLDS | "Redux is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| openedx/frontend-platform:0004-axios-caching-implementation.rst | HOLDS | code | HOLDS | "Axios is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| openedx/paragon:0017-runtime-a11y-validation.rst | HOLDS | code | HOLDS | "React is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| openedx/paragon:0019-scaling-styles-with-design-tokens.rst | HOLDS | code | HOLDS | "Style Dictionary is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| operate-first/blueprint:0004-argocd-apps-of-apps-structure.md | HOLDS | status | HOLDS | "Argo CD is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| operate-first/blueprint:0006-monitoring-structure.md | HOLDS | status | HOLDS | "Prometheus is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | HOLDS |
| thomvaill/log4brains:20200925-use-nextjs-for-static-site-generation.md | HOLDS | code | HOLDS | "Next.js is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| thomvaill/log4brains:20200925-use-prettier-eslint-airbnb-for-the-code-style.md | HOLDS | code | HOLDS | "prettier-eslint is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| thomvaill/log4brains:20200927-avoid-react-fc-type.md | HOLDS | code | HOLDS | "React is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| thomvaill/log4brains:20201103-use-lunr-for-search.md | HOLDS | code | DEAD | "Lunr.js is actively maintained" was contradicted on 2021-08-19 by maintained:lunr:2021-08-19. | HOLDS | HOLDS | HOLDS |
| wmde/fundraising-application:006_Vue.js.md | HOLDS | status | HOLDS | "Vue.js 2 is actively maintained" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
| wmde/fundraising-application:010_Components_Framework.md | HOLDS | status | HOLDS | "Buefy is open source" has no dated evidence either way; nobody has checked it. | HOLDS | HOLDS | DEAD |
