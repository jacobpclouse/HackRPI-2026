PORT ?= 8741
PYTHON ?= python3.12
VENV := .venv
PY := $(VENV)/bin/python
REQ := backend/requirements.txt backend/requirements-job.txt backend/requirements-dev.txt backend/constraints.txt

.PHONY: dev test prepare reference check-job lint fmt clean

# One venv with app, job, and dev dependencies. Rebuilt when any pin changes.
$(VENV)/.installed: $(REQ)
	test -x $(PY) || $(PYTHON) -m venv $(VENV)
	$(PY) -m pip install -q -U pip
	$(PY) -m pip install -q -r backend/requirements-dev.txt
	touch $@

# Same process the Databricks App runs: python backend/app.py.
dev: $(VENV)/.installed
	PORT=$(PORT) $(PY) backend/app.py

test: $(VENV)/.installed
	$(PY) -m pytest -q

prepare: $(VENV)/.installed
	$(PY) backend/scripts/prepare_demo.py

reference: $(VENV)/.installed
	$(PY) backend/scripts/fetch_reference.py

check-job: $(VENV)/.installed
	$(PY) backend/jobs/refresh.py --check

lint: $(VENV)/.installed
	$(PY) -m ruff check backend run.py

fmt: $(VENV)/.installed
	$(PY) -m ruff check --fix backend run.py

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache
