FROM python:3.10.4-buster

WORKDIR /opt/project

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH .
ENV THENEWBOSTON_SETTING_IN_DOCKER true

EXPOSE 8000

RUN set -xe \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && pip install virtualenvwrapper poetry==1.4.2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY ["README.md", "Makefile", "./"]

COPY ["poetry.lock", "pyproject.toml", "./"]
RUN poetry install --no-root

COPY scripts/run-django.sh ./
RUN chmod a+x ./run-django.sh

COPY scripts/run-celery.sh ./
RUN chmod a+x ./run-celery.sh

COPY scripts/run-celery-beat.sh ./
RUN chmod a+x ./run-celery-beat.sh

RUN mkdir local
# TODO(dmu) HIGH: Copying local files with credentials might be not the best idea. Consider changing it
COPY local/settings.prod.py local/settings.prod.py

COPY thenewboston thenewboston
