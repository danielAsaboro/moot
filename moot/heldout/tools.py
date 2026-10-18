"""The extra repositories for study H1, and the tools their ADR titles pick that the backtest's catalogue lacks.

The backtest's catalogue (moot/backtest/tools.py) stays as it was scored. Units from the new repositories are matched on
the backtest's catalogue plus these entries, which were written from the titles alone, before any unit was labelled.
Managed services (S3, GOV.UK PaaS, New Relic) are left out for the backtest's reason: no public commit history.
"""

# Public repositories with ADRs in git that are not in the backtest, from a GitHub code search for
# "0001-record-architecture-decisions.md" (2026-10-21), keeping organisations' repositories with more than a handful of ADRs.
NEW_REPOS = [
    "HHS/Head-Start-TTADP", "alphagov/govuk-docker", "alphagov/govuk_publishing_components", "digitalservicebund/ris-search",
    "DFE-Digital/npq-registration", "ministryofjustice/hmpps-interventions-service", "LBHackney-IT/evidence-api", "apache/james-project",
    "weaveworks/weave-gitops", "cloudfoundry/cli", "wireapp/wire-android", "wireapp/kalium", "incubateur-ademe/territoires-en-transitions",
    "iris-connect/iris-client", "Maptio/maptio", "cljdoc/cljdoc", "athensresearch/athens", "change-metrics/monocle", "asyncapi/studio",
    "DFE-Digital/apply-for-qualified-teacher-status", "DFE-Digital/find-a-lost-trn", "DFE-Digital/dfe-analytics",
    "ministryofjustice/hmpps-person-match", "ministryofjustice/hmpps-accredited-programmes-api", "defenseunicorns/pepr",
    "defenseunicorns/uds-common", "Constellation-Labs/tessellation", "planetary-social/nos", "flyingcircusio/fc-nixos",
    "SmartBear/git-en-boite", "digitalocean/doctl", "eclipse-cdt-cloud/theia-trace-extension",
]

# tool id -> (display name, title regex, GitHub repo whose default-branch history is the maintenance evidence)
EXTRA_TOOLS = {
    "gradle": ("Gradle", r"\bgradle\b", "gradle/gradle"),
    "plantuml": ("PlantUML", r"\bplantuml\b", "plantuml/plantuml"),
    "pact": ("Pact", r"\bpact\b", "pact-foundation/pact-jvm"),
    "scala": ("Scala", r"\bscala\b", "scala/scala"),
    "reactor-netty": ("Reactor Netty", r"reactor-netty", "reactor/reactor-netty"),
    "netty": ("Netty", r"\bnetty\b(?! adoption)", "netty/netty"),
    "pulsar": ("Apache Pulsar", r"\bpulsar\b", "apache/pulsar"),
    "rspamd": ("Rspamd", r"\brspamd\b", "rspamd/rspamd"),
    "cassandra-driver": ("Cassandra Java driver", r"cassandra driver", "apache/cassandra-java-driver"),
    "crowdsec": ("CrowdSec", r"\bcrowdsec\b", "crowdsecurity/crowdsec"),
    "codox": ("Codox", r"\bcodox\b", "weavejester/codox"),
    "grimoire": ("Grimoire", r"\bgrimoire\b", "clojure-grimoire/lib-grimoire"),
    "tachyons": ("Tachyons", r"\btachyons\b", "tachyons-css/tachyons"),
    "sqlite": ("SQLite", r"\bsqlite\b", "sqlite/sqlite"),
    "nomad": ("Nomad", r"\bnomad\b", "hashicorp/nomad"),
    "circleci": ("CircleCI", r"\bcircleci\b", None),
    "protobuf": ("Protocol Buffers", r"\bprotobuf\b", "protocolbuffers/protobuf"),
    "typeorm": ("TypeORM", r"\btypeorm\b", "typeorm/typeorm"),
    "bull": ("Bull", r"\bbull\b", "OptimalBits/bull"),
    "dugite": ("dugite", r"\bdugite\b", "desktop/dugite"),
    "esbuild": ("esbuild", r"\besbuild\b", "evanw/esbuild"),
    "jest": ("Jest", r"\bjest\b", "jestjs/jest"),
    "airbyte": ("Airbyte", r"\bairb\w*te\b", "airbytehq/airbyte"),
    "core-data": ("Core Data", r"core data", None),
    "rails": ("Ruby on Rails", r"ruby on rails|\brails monolith", "rails/rails"),
    "postgres": ("PostgreSQL", r"\bpostgres(ql)?\b", "postgres/postgres"),
}

# How each extra tool shows up in a dependency manifest (moot/heldout/gold.py reads the same manifests as the backtest)
EXTRA_DEPENDENCY = {
    "pact": r"au\.com\.dius\.pact|pact-jvm|\"@pact-foundation/", "reactor-netty": r"reactor-netty", "netty": r"io\.netty|<artifactId>netty",
    "pulsar": r"pulsar-client|org\.apache\.pulsar", "cassandra-driver": r"java-driver-core|com\.datastax\.oss", "codox": r"\bcodox\b",
    "grimoire": r"grimoire", "tachyons": r"\btachyons\b", "protobuf": r"protobuf", "typeorm": r'"typeorm"', "bull": r'"bull"',
    "dugite": r'"dugite"', "esbuild": r'"esbuild"', "jest": r'"jest"', "rails": r"""gem ['"]rails['"]""", "postgres": r"""gem ['"]pg['"]|"pg"\s*:""",
    "scala": r"scala-library|scala\.version|<scala", "sqlite": r"sqlite-jdbc|org\.xerial",
}
# extra manifests these repositories keep (Maven, Gradle, Clojure)
EXTRA_MANIFESTS = ["pom.xml", "build.gradle", "build.gradle.kts", "deps.edn", "project.clj", "libs.versions.toml"]
# infrastructure signals for extra tools: (file pattern, content pattern or None)
EXTRA_INFRA = {"gradle": (r"(^|/)build\.gradle(\.kts)?$|(^|/)gradlew$", None), "nomad": (r"\.nomad(\.hcl)?$", None),
               "circleci": (r"^\.circleci/config\.ya?ml$", None), "plantuml": (r"\.(puml|plantuml)$", None),
               "rspamd": (r"rspamd", None), "crowdsec": (r"crowdsec", None)}

# Words before a tool that mean the title drops it rather than picks it ("Use yarn workspaces instead of lerna")
# ("Don't build on top of Codox", "Removing Pact Contract Testing"); the tool must follow within a few words.
DROPPING = r"\b(instead of|replac\w*|remov\w*|away from|migrat\w* from|deprecat\w*|switch\w* from|against|avoid|don't|do not)\b(\W+\w+){0,4}?\W+"
