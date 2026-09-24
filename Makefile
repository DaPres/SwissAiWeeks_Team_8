# TriageMate - common tasks (Linux/macOS: `make <target>`; on Windows run the python commands directly, see README)
PY ?= python

install:
	$(PY) -m pip install -r requirements.txt

test:
	$(PY) -m pytest tests -q

analyze:            ## reproduce every dataset finding quoted in the README -> eval/dataset_analysis.json
	$(PY) -m triagemate.cli analyze

challenge:          ## triage the challenge file -> outputs/challenge_predictions.{json,csv}
	$(PY) -m triagemate.cli run-challenge

challenge-offline:  ## same, forcing the deterministic engine
	$(PY) -m triagemate.cli run-challenge --offline

eval-offline:       ## stress + validation + holdout with rules only
	$(PY) -m triagemate.cli eval --offline

eval:               ## same with the configured LLM (uses tokens)
	$(PY) -m triagemate.cli eval

smoke:              ## check provider keys in .env (chat, JSON, tools, embeddings, one full ticket)
	$(PY) -m triagemate.cli smoke

run:                ## API + analyst UI on http://127.0.0.1:8765
	$(PY) -m triagemate.cli serve --port 8765

kb:                 ## regenerate the synthetic knowledge base
	$(PY) scripts/generate_kb.py

check: test analyze challenge-offline eval-offline   ## what must be green before every merge
