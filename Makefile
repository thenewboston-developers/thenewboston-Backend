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

.PHONY: up-dependencies-only
up-dependencies-only:
	test -f .env || touch .env
	docker-compose -f docker-compose.dev.yml up --force-recreate db

.PHONY: update
update: install migrate install-pre-commit ;
