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
          
            # DEIN MUSTER: Uhrzeit gefolgt von Temperatur
            # Beispiel: >21:00</wo-date-hour> ... class="temperature"> 5
            # [^>]* greift die dynamischen IDs ab, (\-?\d+) die Temperaturzahl
            pairs = re.findall(r'>(\d{2}:00)</wo-date-hour>.*?class="temperature"[^>]*>\s*(\-?\d+)', content, re.DOTALL)

        try:
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5)
            content = await page.content()
            
            # Wir suchen eine Uhrzeit (XX:00) und danach die nächste Temperatur (X°) 
            # oder die nächste Zahl in der "temperature" Klasse.
            # Der Trick: Wir suchen ALLES, was wie eine Stunde aussieht, 
            # und greifen uns die Zahl direkt danach.
            found_data = []
            # Wir suchen nach Uhrzeit-Mustern (z.B. 22:00)
            all_hours = re.findall(r'(\d{2}:00)', content)
            # Wir suchen nach Temperatur-Mustern (z.B. 5°) oder nackten Zahlen in Temp-Klassen
            all_temps = re.findall(r'(\-?\d+)°', content)

            if len(all_temps) >= 16:
                print(f"ERFOLG: {len(all_temps)} Temperaturen gefunden!")
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                
                # Wir nutzen die aktuelle Stunde als Startpunkt für die 16 Werte
                start_hour = datetime.now().hour
                for i in range(16):
                    current_h = (start_hour + i) % 24
                    h_name = f"{current_h:02d}:00"
                    h_id = f"{current_h:02d}00"
                    t_val = all_temps[i]
                    
                    send_discovery(h_id, h_name)
                    client.publish(f"wetteronline/hourly/{h_id}/temp", t_val, retain=True)
                    print(f"Gelesen -> {h_name}: {t_val}°C")
                
                client.disconnect()
            else:
                print(f"Zu wenig Daten im Quelltext ({len(all_temps)}).")

        except Exception as e:
            print(f"FEHLER: {e}")
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Minuten...")
        time.sleep(1800)
