#!/usr/bin/env bash

set -e

RUN_MANAGE_PY='poetry run python -m thenewboston.manage'

echo 'Collecting static files...'
# TODO(dmu) LOW: Consider moving `collectstatic` to Dockerfile (so it is done at build step)
$RUN_MANAGE_PY collectstatic --no-input

echo 'Running migrations...'
# TODO(dmu) LOW: Consider moving `migrate` to deployment step
$RUN_MANAGE_PY migrate --no-input

exec poetry run daphne thenewboston.project.asgi:application -p 8000 -b 0.0.0.0
