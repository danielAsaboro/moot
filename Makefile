.PHONY: db seed serve demo eval eval-scale eval-e2e test extract reset
MODULE=$(shell python3 -c "import redislite,os;print(os.path.dirname(redislite.__file__))" 2>/dev/null)

db:        ## start an embedded FalkorDB on :6379 (pip install falkordblite) when you have no Docker
	$(MODULE)/bin/redis-server --port 6379 --loadmodule $(MODULE)/bin/falkordb.so --dir .falkordb --daemonize yes || true
	@sleep 1 && redis-cli ping
seed:      ## idempotent import of data/graph.json
	python3 -m moot.cli seed
reset:     ## drop the demo graph and reseed
	python3 -m moot.cli seed --fresh
serve:     ## web app + API on :8000
	python3 -m moot.cli serve
demo: db seed serve
eval:      ## retrieval eval, no model needed -> eval/results.md
	python3 eval/eval_retrieval.py
eval-scale: ## noise scaling + verdict eval, no model needed -> eval/results_scale.md
	python3 eval/eval_scale.py
eval-e2e:  ## model-in-the-loop eval -> eval/results_e2e.md (needs ANTHROPIC_API_KEY)
	python3 eval/eval_e2e.py
extract:   ## LLM extraction from data/corpus -> data/extracted.json (needs ANTHROPIC_API_KEY)
	python3 -m moot.cli extract
test:
	python3 -m pytest -q
