# Developer convenience targets

.PHONY: run test start stop logs deploy migrate upgrade

run:
	./scripts/start.sh

test:
	python -m venv .venv; \
	source .venv/bin/activate && pip install -r requirements.txt && pytest -q

start:
	./scripts/start.sh bg

stop:
	./scripts/stop.sh

logs:
	tail -f logs/server.log

migrate:
	source .venv/bin/activate && flask db migrate -m "$(m)"

upgrade:
	source .venv/bin/activate && flask db upgrade

deploy:
	./scripts/deploy_local.sh $$DEPLOY_SSH_TARGET
