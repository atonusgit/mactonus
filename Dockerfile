FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    curl \
    git \
    cron \
    nano \
    locales \
    xz-utils \
    && sed -i '/en_US.UTF-8/s/^# //' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV PYTHONIOENCODING=utf-8

RUN mkdir -p /vault

RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

WORKDIR /root

CMD ["sh", "-c", "hermes gateway & cron -f"]
#CMD ["cron", "-f"]
