FROM homeassistant/aarch64-base-debian:bookworm

# 1. System-Pakete installieren
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    chromium \
    chromium-driver \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# 2. Python-Abhängigkeiten (Aufruf via python3 -m pip)
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# 3. Playwright installieren
RUN python3 -m pip install --no-cache-dir --break-system-packages playwright

# 4. Umgebungsvariablen
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV PLAYWRIGHT_CHROME_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /usr/src/app
COPY scraper.py .
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
