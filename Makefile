.PHONY: build
build:
	# We are not building with Docker compose on purpose, so we can have just one image (and probably save disk space)
	docker build . -t thenewboston-backend:current

.PHONY: build-no-cache
build-no-cache:
	# We are not building with Docker compose on purpose, so we can have just one image (and probably save disk space)
	docker build . -t thenewboston-backend:current --no-cache

.PHONY: update-docker-compose-yaml
update-docker-compose-yaml:
	cp docker-compose.yml ~/

.PHONY: docker-compose-down
docker-compose-down:
	cd; docker compose down

.PHONY: run-production
run-production:  # purposefully do not depend on `build` target
	cd; docker compose up -d --no-build --force-recreate

.PHONY: run-development-no-build
run-development-no-build:
	# docker-compose.yml is inherited and overridden by docker-compose.dev.yml
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --force-recreate

.PHONY: run-development
run-development: build run-development-no-build

.PHONY: deploy
deploy: build-no-cache docker-compose-down update-docker-compose-yaml run-production;

.PHONY: deploy-cleanup
deploy-cleanup:
	docker image prune -f
	docker builder prune -f

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
	# docker-compose.yml is inherited and overridden by docker-compose.dev.yml
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --force-recreate db redis

.PHONY: run-server
run-server:
	poetry run python -m thenewboston.manage runserver

.PHONY: run-daphne
run-daphne:
# TODO(dmu): Convert to having `run-server-prod` using `./run-django.sh` for consistency with production and Ccelery
	poetry run python -m thenewboston.manage collectstatic --no-input
	poetry run daphne thenewboston.project.asgi:application -p 8000 -b 127.0.0.1

.PHONY: run-order-processing-engine
run-order-processing-engine:
	./scripts/run-order-processing-engine.sh

.PHONY: run-celery
run-celery:
	./scripts/run-celery.sh

.PHONY: run-celery-beat
run-celery-beat:
	./scripts/run-celery-beat.sh

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
	poetry run pytest -vv -rs --show-capture=no --cov=thenewboston --cov-report=html:./tmp/coverage/html --cov-report=xml:./tmp/coverage/coverage.xml

.PHONY: lint-and-test
lint-and-test: lint test ;

.PHONY: update
update: install migrate install-pre-commit ;

.PHONY: diff-cover
diff-cover:
	poetry run diff-cover --format html:./tmp/coverage/diff-cover.html --compare-branch origin/master ./tmp/coverage/coverage.xml

.PHONY: test-and-diff-cover
test-and-diff-cover: test-cov diff-cover ;

.PHONY: prod-dump-db
prod-dump-db:
	PGPASSWORD=$(password) pg_dump -h thenewboston-new.cif0ormi7x5n.us-west-2.rds.amazonaws.com -U thenewboston -F p -b -v -O -f "$(destination)" thenewboston

.PHONY: restore-db-dump
restore-db-dump:
	PGPASSWORD=thenewboston psql -h localhost -U thenewboston -c "CREATE DATABASE $(dbname);"
	PGPASSWORD=thenewboston psql -h localhost -U thenewboston -d "$(dbname)" -f "$(source)"

.PHONY: prod-shell
prod-shell:
	ssh ubuntu@thenewboston.network
