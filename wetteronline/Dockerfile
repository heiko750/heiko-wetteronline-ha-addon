ARG BUILD_FROM
FROM ${BUILD_FROM}

# 1. System-Pakete (Python, Pip und der Browser selbst)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    chromium \
    nss \
    freetype \
    harfbuzz \
    ca-certificates \
    ttf-freefont \
    dbus

# 2. Python-Module installieren
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# 3. Playwright Python-Interface ohne Browser-Downloads installieren
# Wir nutzen --no-deps oder installieren es separat, um ARM-Probleme zu umgehen
RUN pip3 install --no-cache-dir --break-system-packages playwright

# 4. Umgebungsvariablen (Zwingend für ARM/Alpine)
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROME_EXECUTABLE_PATH=/usr/bin/chromium-browser

WORKDIR /usr/src/app
COPY scraper.py .
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
