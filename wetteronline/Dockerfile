ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install pip (falls nicht vorhanden)
RUN apk add --no-cache py3-pip

# Install Python dependencies
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Erstelle Verzeichnis und kopiere Skripte
WORKDIR /usr/src/app
COPY scraper.py .
COPY run.sh /run.sh
RUN chmod a+x /run.sh

# Das S6-Overlay startet automatisch /run.sh, wenn kein CMD angegeben ist 
# oder wenn wir es explizit als Entrypoint nutzen. 
# Bei HA-Base-Images ist das Beste:
CMD [ "/run.sh" ]
