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

# Asenna Node.js 22 (pi-coding-agent vaatii sen; slim-imagessa ei ole nodea)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Asenna pi.dev-työkalu npm:llä. pi.dev/install.sh vain delegoi tähän eikä toimi
# ilman terminaalia Docker-buildissa, joten kutsutaan npm:ää suoraan.
RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent

WORKDIR /root

# pi on pelkkä interaktiivinen CLI (ei gateway-tilaa), joten kontti ajaa cronin
# ja — jos Telegram-token on annettu — Telegram-sillan, joka ajaa pi:tä headless.
# Silta uudelleenkäynnistyy jos se kaatuu. pi:tä käytetään myös: docker exec -it mactonus pi
CMD ["sh", "-c", "if [ -n \"$TELEGRAM_BOT_TOKEN\" ]; then (while true; do python3 /root/scripts/telegram/telegram_bridge.py; echo 'silta kaatui, uudelleenkäynnistys 5 s päästä'; sleep 5; done >> /tmp/telegram/silta.log 2>&1) & fi; cron -f"]
