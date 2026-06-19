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

RUN curl -fsSL https://pi.dev/install.sh | sh

# pi:n asennin sijoittaa binäärin yleensä ~/.local/bin:iin → varmistetaan PATH
ENV PATH="/root/.local/bin:${PATH}"

WORKDIR /root

# pi on pelkkä interaktiivinen CLI (ei gateway-/daemon-tilaa kuten hermesissä),
# joten kontti ajaa vain cronin. pi:tä käytetään: docker exec -it mactonus pi
CMD ["cron", "-f"]
