.PHONY: install
install:
	poetry install

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

.PHONY: update
update: install migrate ;
