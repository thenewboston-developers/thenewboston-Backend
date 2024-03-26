#!/usr/bin/env bash

exec poetry run celery -A thenewboston.project beat -l INFO
