import asyncio
import re
import json
import time
import os
from datetime import datetime
from playwright.async_api import async_playwright
import paho.mqtt.client as mqtt

# Konfiguration
MQTT_HOST = "172.30.32.1"
MQTT_USER = os.getenv("MQTT_USER", "mqtt-user")
MQTT_PASS = os.getenv("MQTT_PASSWORD")
LOCATION = os.getenv("LOCATION", "grafing")
URL = f"https://www.wetteronline.de/wetter/{LOCATION.strip('/')}"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def send_discovery(h_id, h_name):
    topic = f"homeassistant/sensor/wo_{h_id}/config"
    payload = {
        "name": f"WO {h_name}",
        "state_topic": f"wetteronline/hourly/{h_id}/temp",
        "unit_of_measurement": "°C",
        "unique_id": f"wo_t_{h_id}",
        "device_class": "temperature",
        "state_class": "measurement"
    }
    client.publish(topic, json.dumps(payload), retain=True)

async def scrape():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        print(f"STARTE PRÄZISIONS-ABFRAGE: {URL}")
        try:
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5)
            content = await page.content()
            
            # DEIN MUSTER: Uhrzeit gefolgt von Temperatur
            # Beispiel: >21:00</wo-date-hour> ... class="temperature"> 5
            # [^>]* greift die dynamischen IDs ab, (\-?\d+) die Temperaturzahl
            pairs = re.findall(r'>(\d{2}:00)</wo-date-hour>.*?class="temperature"[^>]*>\s*(\-?\d+)', content, re.DOTALL)

            if pairs:
                print(f"ERFOLG: {len(pairs)} stündliche Paare gefunden!")
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                
                for h_name, t_val in pairs[:24]: # Nimm die nächsten 24 verfügbaren Stunden
                    h_id = h_name.replace(":", "")
                    send_discovery(h_id, h_name)
                    client.publish(f"wetteronline/hourly/{h_id}/temp", t_val, retain=True)
                    print(f"Gelesen -> {h_name}: {t_val}°C")
                
                client.disconnect()
            else:
                print("Muster nicht gefunden. Versuche Fallback-Suche...")
                # Falls die Tags fehlen, nehmen wir alle Zahlen mit ° (dein alter Erfolgsweg)
                fallback_temps = re.findall(r'(\-?\d+)°', content)
                print(f"Fallback ergab {len(fallback_temps)} Treffer.")

        except Exception as e:
            print(f"FEHLER: {e}")
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Minuten...")
        time.sleep(1800)
