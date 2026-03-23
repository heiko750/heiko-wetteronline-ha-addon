ARG BUILD_FROM
FROM ${BUILD_FROM}

# 1. System-Pakete installieren (inkl. Python3, Pip und Chromium für Playwright)
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

# 2. Python-Abhängigkeiten kopieren und installieren
COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# 3. Playwright-Umgebungsvariablen setzen
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROME_EXECUTABLE_PATH=/usr/bin/chromium-browser

# 4. App-Dateien vorbereiten
WORKDIR /usr/src/app
COPY scraper.py .
COPY run.sh /run.sh
RUN chmod a+x /run.sh

# 5. Startbefehl
CMD [ "/run.sh" ]
