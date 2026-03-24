import asyncio
import re
import json
import time
import os
from datetime import datetime
from playwright.async_api import async_playwright
import paho.mqtt.client as mqtt

MQTT_HOST = "172.30.32.1"
# Diese Werte holt sich das Add-on aus deiner config.json / UI
LOCATION = os.getenv("LOCATION", "grafing")
MQTT_USER = os.getenv("MQTT_USER")
MQTT_PASS = os.getenv("MQTT_PASSWORD")

URL = f"https://www.wetteronline.de{LOCATION.lstrip('/')}"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def send_discovery(h_id, h_name):
    """Erstellt die Sensoren automatisch in Home Assistant"""
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
        print(f"Abfrage läuft: {URL}")
        try:
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5)
            content = await page.content()
            
            # Extraktion der Temperaturen (Zahlen vor dem ° Symbol)
            temps = re.findall(r'(\d+)°', content)

            if len(temps) >= 16:
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                client.loop_start()
                time.sleep(1)
                
                start_hour = datetime.now().hour
                for i in range(16):
                    current_h = (start_hour + i) % 24
                    h_id = f"{current_h:02d}00"
                    h_name = f"{current_h:02d}:00"
                    t_val = temps[i]
                    
                    send_discovery(h_id, h_name)
                    client.publish(f"wetteronline/hourly/{h_id}/temp", t_val, retain=True)
                    print(f"Update: {h_name} -> {t_val}°C")
                
                time.sleep(2)
                client.loop_stop()
                client.disconnect()
            else:
                print(f"Zu wenig Daten gefunden ({len(temps)}).")
        except Exception as e:
            print(f"Fehler: {e}")
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Minuten bis zum nächsten Scan...")
        time.sleep(1800)
