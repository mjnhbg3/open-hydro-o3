.PHONY: lint test install-services shadow-run clean venv

VENV = venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

venv:
	python -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

lint: venv
	$(VENV)/bin/ruff check app/ scripts/ tests/
	$(VENV)/bin/black --check app/ scripts/ tests/

format: venv
	$(VENV)/bin/ruff check --fix app/ scripts/ tests/
	$(VENV)/bin/black app/ scripts/ tests/

test: venv
	$(VENV)/bin/pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=80

shadow-run: venv
	@echo "Running shadow simulation with sample data..."
	$(PYTHON) scripts/shadow_validator.py --data tests/data/sensors_sample.csv

install-services:
	@echo "Installing systemd services..."
	sudo ./scripts/install_services.sh

clean:
	rm -rf $(VENV)
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete
	rm -rf .pytest_cache
	rm -rf .coverage

backup:
	./backup/weekly_backup.sh

run-sensor-poll: venv
	$(PYTHON) scripts/sensor_poll.py

run-control-loop: venv
	$(PYTHON) scripts/control_loop.py

run-kpi-rollup: venv
	$(PYTHON) scripts/kpi_rollup.py

run-brain-sync: venv
	$(PYTHON) scripts/daily_brain_sync.py