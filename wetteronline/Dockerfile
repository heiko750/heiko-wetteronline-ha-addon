ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install pip (falls nicht vorhanden)
RUN apk add --no-cache py3-pip

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Copy your Python script
COPY scraper.py /app/scraper.py

# Use s6-overlay init system

