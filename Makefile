# Developer convenience targets

.PHONY: run test start stop logs deploy

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

deploy:
	./scripts/deploy_local.sh $$DEPLOY_SSH_TARGET
