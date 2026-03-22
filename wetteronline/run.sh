#!/usr/bin/env bash
echo "Starting WetterOnline Scraper Add-on..."

LOCATION=$(jq -r '.location' /data/options.json)
INTERVAL=$(jq -r '.interval' /data/options.json)
MQTT_HOST=$(jq -r '.mqtt_host' /data/options.json)
MQTT_PORT=$(jq -r '.mqtt_port' /data/options.json)

export LOCATION
export INTERVAL
export MQTT_HOST
export MQTT_PORT

while true; do
    python3 /scraper.py
    sleep $((INTERVAL * 60))
done
