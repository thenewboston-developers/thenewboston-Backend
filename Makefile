# TODO(dmu) MEDIUM: Upgrade docker everywhere and remove the following workaround
DOCKER_COMPOSE_COMMAND := $(shell command -v docker-compose 2> /dev/null || echo "docker compose")

.PHONY: install
install:
	poetry install

.PHONY: install-pre-commit
install-pre-commit:
	poetry run pre-commit uninstall; poetry run pre-commit install

.PHONY: lint
lint:
	poetry run pre-commit run --all-files

.PHONY: migrate
migrate:
	poetry run python -m thenewboston.manage migrate

.PHONY: migrations
migrations:
	poetry run python -m thenewboston.manage makemigrations

.PHONY: run-dependencies
run-dependencies:
	test -f .env || touch .env
	${DOCKER_COMPOSE_COMMAND} -f docker-compose.dev.yml up --force-recreate db redis

.PHONY: run-server
run-server:
	poetry run python -m thenewboston.manage runserver

.PHONY: shell
shell:
	poetry run python -m thenewboston.manage shell

.PHONY: superuser
superuser:
	poetry run python -m thenewboston.manage createsuperuser

.PHONY: test
test:
	poetry run pytest -v -rs -n auto --show-capture=no

.PHONY: test-detailed
test-detailed:
	poetry run pytest -vv -rs -s

.PHONY: update
update: install migrate install-pre-commit ;

.PHONY: worker
worker:
	poetry run celery -A thenewboston.project worker -l INFO
