FROM python:3.10.4-buster

WORKDIR /opt/project

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH .
ENV THENEWBOSTON_SETTING_IN_DOCKER true

RUN set -xe \
    && apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && pip install virtualenvwrapper poetry==1.4.2 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY ["poetry.lock", "pyproject.toml", "./"]
RUN poetry install --no-root

COPY ["README.md", "Makefile", "./"]
COPY thenewboston thenewboston
COPY local local

EXPOSE 8000

COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod a+x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
