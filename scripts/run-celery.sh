#!/usr/bin/env bash
exec poetry run celery -A thenewboston.project worker -l INFO
