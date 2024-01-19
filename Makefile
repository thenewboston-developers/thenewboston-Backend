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

.PHONY: run-celery
run-celery:
	poetry run celery -A thenewboston.project worker -l INFO

.PHONY: run-dependencies
run-dependencies:
	test -f .env || touch .env
	${DOCKER_COMPOSE_COMMAND} -f docker-compose.dev.yml up --force-recreate db redis

.PHONY: run-server
run-server:
	poetry run python -m thenewboston.manage runserver

.PHONY: run-daphne
run-daphne:
	poetry run python -m thenewboston.manage collectstatic --no-input
	poetry run daphne thenewboston.project.asgi:application -p 8000 -b 127.0.0.1

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
