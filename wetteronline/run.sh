#!/usr/bin/with-contenv bashio

bashio::log.info "Starting WetterOnline scraper..."

python3 /usr/src/app/scraper.py

