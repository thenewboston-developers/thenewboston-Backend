.PHONY: build
build:
	# We are not building with Docker compose on purpose, so we can have just one image (and probably save disk space)
	docker build . -t thenewboston-backend:current --no-cache

.PHONY: run-production
run-production:  # purposefully do not depend on `build` target
	docker compose up -d --force-recreate

.PHONY: run-development
run-development: build
	# docker-compose.yml is inherited and overridden by docker-compose.dev.yml
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --force-recreate

.PHONY: deploy
deploy: build run-production;

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

.PHONY: run-celery-beat
run-celery-beat:
	poetry run celery -A thenewboston.project beat -l INFO

.PHONY: run-dependencies
run-dependencies:
	# docker-compose.yml is inherited and overridden by docker-compose.dev.yml
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --force-recreate db redis

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

.PHONY: dbshell
dbshell:
	poetry run python -m thenewboston.manage dbshell

.PHONY: superuser
superuser:
	poetry run python -m thenewboston.manage createsuperuser

.PHONY: test
test:
	poetry run pytest -v -rs --show-capture=no

.PHONY: test-detailed
test-detailed:
	poetry run pytest -vv -rs -s

.PHONY: test-cov
test-cov:
	poetry run pytest -vv -rs --show-capture=no --cov=thenewboston --cov-report=html:./tmp/coverage

.PHONY: lint-and-test
lint-and-test: lint test ;

.PHONY: update
update: install migrate install-pre-commit ;
