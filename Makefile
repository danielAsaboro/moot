.PHONY: judge-check ui ui-dev db seed serve demo eval eval-scale eval-gate eval-ablation verify eval-e2e test extract reset realworld backtest backtest-score erag erag-judged
MODULE=$(shell python3 -c "import redislite,os;print(os.path.dirname(redislite.__file__))" 2>/dev/null)

db:        ## start an embedded FalkorDB on :6379 (pip install falkordblite) when you have no Docker
	$(MODULE)/bin/redis-server --port 6379 --loadmodule $(MODULE)/bin/falkordb.so --dir .falkordb --daemonize yes || true
	@sleep 1 && redis-cli ping
realworld: ## re-check real public ADRs against GitHub and OSV (network) -> data/realworld/, then reseed
	python3 -m moot.cli realworld && python3 -m moot.cli seed
seed:      ## idempotent import of data/graph.json (+ data/realworld/graph.json into public_adrs)
	python3 -m moot.cli seed
reset:     ## drop the demo graph and reseed
	python3 -m moot.cli seed --fresh
ui:        ## build the Next.js UI to frontend/out (served by `make serve`)
	cd frontend && npm ci --no-fund --no-audit && npm run build
ui-dev:    ## Next.js dev server on :3000 against the API on :8000
	cd frontend && npm run dev
serve:     ## web app + API on :8000
	python3 -m moot.cli serve
demo:     ## one command: FalkorDB, seed, build the UI if needed, serve on :8000
	$(MAKE) db seed $(if $(wildcard frontend/out/index.html),,ui) serve
eval:      ## retrieval eval, no model needed -> eval/results.md
	python3 eval/eval_retrieval.py
eval-scale: ## noise scaling + verdict eval, no model needed -> eval/results_scale.md
	python3 eval/eval_scale.py
eval-gate: ## validity gate eval, no model needed -> eval/results_gate.md
	python3 eval/eval_gate.py
eval-ablation: ## graph ablation in both directions (pre-registered, docs/studies.md S1) -> eval/results_ablation.md
	python3 eval/eval_ablation.py
verify:    ## re-run the deterministic evals and check every README number against their JSON; non-zero on drift
	python3 -m moot.cli verify --rerun
backtest:  ## rewind 30 public repos' ADR history and score the gate against what maintainers later did (network, ~1.5 GB of git) -> eval/results_backtest.md
	python3 -m moot.backtest.labels && python3 -m moot.backtest.run && python3 -m moot.backtest.code && python3 eval/eval_backtest.py
backtest-score: ## re-score the committed backtest snapshot, offline
	python3 eval/eval_backtest.py
erag:      ## EnterpriseRAG-Bench blind supersession cut vs Canon's oracle, deterministic (downloads 1.4 GB to ../erag-data, needs FalkorDB) -> eval/results_erag.md
	python3 -m moot.bench_erag.fetch && python3 -m moot.bench_erag.corpus && python3 -m moot.bench_erag.pools && python3 -m moot.bench_erag.cut && python3 -m moot.bench_erag.cut v2 && python3 eval/eval_erag.py
erag-judged: ## + answers and the benchmark's own judge, 3 runs (needs ANTHROPIC_API_KEY and ../erag-harness)
	python3 eval/eval_erag.py --answer --judge
eval-e2e:  ## model-in-the-loop eval -> eval/results_e2e.md (needs ANTHROPIC_API_KEY)
	python3 eval/eval_e2e.py
extract:   ## LLM extraction from data/corpus -> data/extracted.json (needs ANTHROPIC_API_KEY)
	python3 -m moot.cli extract
judge-check: ## everything a judge can check offline in one go: tests (incl. NetworkX cross-checks), every README number re-derived, the held-out gold hash
	python3 -m pytest -q && python3 -m moot.cli verify --rerun && python3 eval/eval_heldout.py && python3 eval/eval_router.py && echo "judge-check: all green"
test:
	python3 -m pytest -q
