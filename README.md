# WetterOnline Add-on Repository

This Repository contains the Home Assistant Add-on "WetterOnline Scraper".
Motivation for the Add-on: I checked severeal avaialble weather services like DWD or AccuWeather over months, none of them provide a so precise forecast like wetteronline for my home town.
The Add-on, optimized for ODROID-N2+ / HA Blue, scrapes from wetteronline the temperature, weather condition as well as wind for the next 24 hours and makes them available as entities via MQTT.
In case you install this Add-on and notice problems:
1: check, whether you added in the config of the Add-on your MQTT user name and password as well as location 
2: for debugging you could use the following command:
docker exec -it -e MQTT_USER='your username' -e MQTT_PASSWORD='your password' addon_cdfa4b18_wetteronline python3 /usr/src/app/scraper.py
This command is working in the "Advanced SSH & Web Terminal" once you are logged in as root via port 22, it feedbacks useful details for debugging.
"cdfa4b18" is my repo directory, you have to replace with your one, it can be identified with: docker exec hassio_supervisor ls -la /data/addons/git
