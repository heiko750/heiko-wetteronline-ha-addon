ARG BUILD_FROM=ghcr.io/hassio-addons/base-python:17.0.0
FROM ${BUILD_FROM}

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy your Python script
COPY scraper.py /usr/src/app/scraper.py

# Copy run script
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
