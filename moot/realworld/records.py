"""Real, public architecture decision records that pick a named open-source tool.

Each record points at the ADR on GitHub and quotes it verbatim (the checker refuses a record whose
quote is not in the fetched text). The ADRs state their own reasons; Moot checks the reasons every
one of them leaves unwritten, because they were true when the decision was made:

  the tool is still maintained · the tool is still open source · its current release has no known vulnerability

Five repositories: ministryofjustice/cloud-platform, alphagov/govuk-infrastructure, alphagov/govuk-aws,
thomvaill/log4brains and backstage/backstage. Dates are the ADR's own date, or the first commit of the
file when the ADR carries none (Backstage).
"""

# tool id -> (display name, GitHub repo of the tool, OSV package (ecosystem, name) or None)
TOOLS = {
    "concourse": ("Concourse CI", "concourse/concourse", ("Go", "github.com/concourse/concourse")),
    "kubernetes": ("Kubernetes", "kubernetes/kubernetes", ("Go", "k8s.io/kubernetes")),
    "opa": ("Open Policy Agent", "open-policy-agent/opa", ("Go", "github.com/open-policy-agent/opa")),
    "karpenter": ("Karpenter", "kubernetes-sigs/karpenter", ("Go", "sigs.k8s.io/karpenter")),
    "tf-aws-eks": ("terraform-aws-eks module", "terraform-aws-modules/terraform-aws-eks", None),
    "aws-lbc": ("AWS Load Balancer Controller", "kubernetes-sigs/aws-load-balancer-controller", ("Go", "sigs.k8s.io/aws-load-balancer-controller")),
    "helm": ("Helm", "helm/helm", ("Go", "helm.sh/helm/v4")),
    "fluent-bit": ("Fluent Bit", "fluent/fluent-bit", None),
    "elasticsearch": ("Elasticsearch", "elastic/elasticsearch", ("Maven", "org.elasticsearch:elasticsearch")),
    "external-secrets": ("external-secrets", "external-secrets/external-secrets", ("Go", "github.com/external-secrets/external-secrets")),
    "external-dns": ("external-dns", "kubernetes-sigs/external-dns", ("Go", "sigs.k8s.io/external-dns")),
    "dex": ("Dex", "dexidp/dex", ("Go", "github.com/dexidp/dex")),
    "prometheus-adapter": ("Prometheus Adapter", "kubernetes-sigs/prometheus-adapter", ("Go", "sigs.k8s.io/prometheus-adapter")),
    "crossplane": ("Crossplane", "crossplane/crossplane", ("Go", "github.com/crossplane/crossplane/v2")),
    "pkl": ("Pkl", "apple/pkl", ("Maven", "org.pkl-lang:pkl-core")),
    "gatekeeper": ("OPA Gatekeeper", "open-policy-agent/gatekeeper", ("Go", "github.com/open-policy-agent/gatekeeper/v3")),
    "puppet": ("Puppet", "puppetlabs/puppet", ("RubyGems", "puppet")),
    "redis": ("Redis", "redis/redis", None),
    "lerna": ("Lerna", "lerna/lerna", ("npm", "lerna")),
    "prettier-eslint": ("prettier-eslint", "prettier/prettier-eslint", ("npm", "prettier-eslint")),
    "airbnb": ("Airbnb ESLint config", "airbnb/javascript", ("npm", "eslint-config-airbnb")),
    "lunr": ("Lunr.js", "olivernn/lunr.js", ("npm", "lunr")),
    "mdx": ("MDX", "mdx-js/mdx", ("npm", "@mdx-js/mdx")),
    "msw": ("Mock Service Worker", "mswjs/msw", ("npm", "msw")),
    "luxon": ("Luxon", "moment/luxon", ("npm", "luxon")),
    "node-fetch": ("node-fetch", "node-fetch/node-fetch", ("npm", "node-fetch")),
}

MOJ, GI, GA, L4B, BS = ("ministryofjustice/cloud-platform", "alphagov/govuk-infrastructure", "alphagov/govuk-aws",
                         "thomvaill/log4brains", "backstage/backstage")
P = {MOJ: "architecture-decision-record", GI: "docs/architecture/decisions", GA: "docs/architecture/decisions",
     L4B: "docs/adr", BS: "docs/architecture-decisions"}

# id, repo, file, title, date, tools, verbatim quote, the ADR's own status when it is no longer accepted
RECORDS = [
    ("moj-003", MOJ, "003-Use-Concourse-CI.md", "Use Concourse CI", "2018-03-28", ["concourse"],
     "Replace self hosted Jenkins with self hosted Concourse CI pipeline", None),
    ("moj-004", MOJ, "004-use-kubernetes-for-container-management.md", "Use Kubernetes for container management", "2018-04-10", ["kubernetes"],
     "Use Kubernetes as the container management component and core technology for our new hosting platform.", None),
    ("moj-011", MOJ, "011-Introduce-Open-Policy-Agent.md", "Introduce Open Policy Agent", "2019-06-07", ["opa"],
     "Eventually we decided to introduce the [Open Policy Agent]", None),
    ("moj-047", MOJ, "047-use-karpenter-for-scaling.md", "Use Karpenter for scaling", "2026-04-21", ["karpenter"],
     "We will use **Karpenter** as the primary scaling solution", None),
    ("gi-0002", GI, "0002-use-aws-eks-terraform-module.md", "Use the aws-eks Terraform module", "2021-08-10", ["tf-aws-eks"],
     "Adopt the [existing Terraform registry EKS module]", None),
    ("gi-0004", GI, "0004-use-aws-load-balancer-controller-for-edge-traffic-services.md", "Use AWS Load Balancer Controller for edge traffic", "2021-08-12", ["aws-lbc"],
     "Use the [AWS Load Balancer Controller]", None),
    ("gi-0006", GI, "0006-use-helm-for-application-package-management.md", "Use Helm for application package management", "2021-08-16", ["helm"],
     "Use Helm v3+.", None),
    ("gi-0007", GI, "0007-use-fluentbit-elasticsearch-and-kibana-for-application-logs.md", "Use Fluent Bit, Elasticsearch and Kibana for application logs", "2021-08-16",
     ["fluent-bit", "elasticsearch"], "Use a **Fluent Bit** `DaemonsSet` with AWS Elasticsearch Service.", "deprecated"),
    ("gi-0008", GI, "0008-use-external-secrets-for-secrets-storage.md", "Use external-secrets for secrets storage", "2021-08-26", ["external-secrets"],
     "is also on a deprecation", None),
    ("gi-0009", GI, "0009-use-external-dns-for-dns-record-management.md", "Use external-dns for DNS record management", "2021-08-27", ["external-dns"],
     "Use [`external-dns`]", None),
    ("gi-0010", GI, "0010-use-dex-idp-for-user-web-authentication.md", "Use Dex for user web authentication", "2021-12-01", ["dex"],
     "Use [Dex](https://dexidp.io) as a Single Sign-On (SSO) service", None),
    ("gi-0013", GI, "0013-expose-external-metrics-for-hpa.md", "Expose external metrics for HPA with Prometheus Adapter", "2025-06-03", ["prometheus-adapter"],
     "Adopt the **Prometheus Adapter** Helm chart", None),
    ("gi-0018", GI, "0018-use-concourse-ci.md", "Use Concourse CI", "2025-08-12", ["concourse"],
     "the team decided to pursue Concourse as its CI/CD tool", None),
    ("gi-0020", GI, "0020-use-crossplane-for-abstraction.md", "Use Crossplane for abstraction", "2025-10-20", ["crossplane"],
     "We have decided that we want to use Crossplane", None),
    ("gi-0022", GI, "0022-use-pkl-for-configuration.md", "Use Pkl for configuration", "2025-11-06", ["pkl"],
     "it was the most mature, well-supported, and feature rich", None),
    ("gi-0023", GI, "0023-use-opa-gatekeeper.md", "Use OPA Gatekeeper", "2026-07-07", ["gatekeeper"],
     "it is a mature CNCF graduated", None),
    ("ga-0006", GA, "0006-puppet-architecture.md", "Puppet architecture", "2017-07-04", ["puppet"],
     "Use a Puppetmaster to not diverge from current architecture in the initial iteration.", None),
    ("ga-0025", GA, "0025-use-elasticache-for-redis.md", "Use Elasticache for Redis", "2017-09-04", ["redis"],
     "We are using Elasticache instead of provisioning our own Redis instances.", None),
    ("l4b-lerna", L4B, "20200925-multi-packages-architecture-in-a-monorepo-with-yarn-and-lerna.md", "Monorepo with Yarn and Lerna", "2020-09-25", ["lerna"],
     "Yarn + Lerna seems to be a very good practice used by a lot of other open-source projects", None),
    ("l4b-style", L4B, "20200925-use-prettier-eslint-airbnb-for-the-code-style.md", "Use Prettier-ESLint Airbnb for the code style", "2020-09-25",
     ["prettier-eslint", "airbnb"], "Airbnb code style is widely used", None),
    ("l4b-mdx", L4B, "20201026-the-core-api-is-responsible-for-enhancing-the-adr-markdown-body-with-mdx.md", "Enhance the ADR markdown body with MDX", "2020-10-26", ["mdx"],
     "the core API is responsible (with MDX)", None),
    ("l4b-lunr", L4B, "20201103-use-lunr-for-search.md", "Use Lunr for search", "2020-11-03", ["lunr"],
     "Chosen option: \"Option 2: Lunr.js\".", None),
    ("bs-007", BS, "adr007-use-msw-to-mock-service-requests.md", "Use MSW to mock HTTP requests", "2020-07-14", ["msw"],
     "should be mocked by using `msw`", None),
    ("bs-010", BS, "adr010-luxon-date-library.md", "Use the Luxon date library", "2021-01-18", ["luxon"],
     "We will use [Luxon]", None),
    ("bs-013", BS, "adr013-use-node-fetch.md", "Use node-fetch for HTTP fetching", "2021-12-21", ["node-fetch"],
     "Backend (node) packages should use the `node-fetch` package", "superseded"),
]


# Records their own repository has since retired. Each becomes a dated (Evidence)-[:RETIRES]->(Decision) edge, so the
# verdict is RETIRED from that day and the record is no longer audited as if it were in force. The date is the commit
# that first carries the status text; the quote must be verbatim in the retiring file, as for RECORDS.
# record id -> (evidence id, repo, file, title, date, verbatim quote, commit)
RETIREMENTS = {
    "bs-013": ("bs-adr014", BS, "adr014-use-fetch.md", "Backstage ADR014: Proper use of HTTP fetching libraries (supersedes ADR013)",
               "2024-11-29", "Until now we have been recommending the use of `node-fetch` in Node.js contexts", "3ecfb12185"),
    "gi-0007": ("gi-0007-deprecated", GI, "0007-use-fluentbit-elasticsearch-and-kibana-for-application-logs.md",
                "GOV.UK ADR 0007 status changed to Deprecated", "2025-07-21", "Deprecated (no superseding ADR)", "bdda1339fa"),
}


def source_url(repo: str, file: str) -> str:
    return f"https://github.com/{repo}/blob/HEAD/{P[repo]}/{file}"


def raw_url(repo: str, file: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/HEAD/{P[repo]}/{file}"
