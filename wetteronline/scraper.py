import asyncio
import re
import json
import time
import os
from datetime import datetime
from playwright.async_api import async_playwright
import paho.mqtt.client as mqtt

# Konfiguration aus der Add-on UI
MQTT_HOST = "172.30.32.1"
MQTT_USER = os.getenv("MQTT_USER", "mqtt-user")
MQTT_PASS = os.getenv("MQTT_PASSWORD")
LOCATION = os.getenv("LOCATION", "grafing")

# URL sicher zusammenbauen
URL = f"https://www.wetteronline.de/wetter/{LOCATION.strip('/')}"

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
        browser = await p.chromium.launch(
            executable_path="/usr/bin/chromium", 
            headless=True, 
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        page = await browser.new_page()
        print(f"STARTE PRÄZISIONS-ABFRAGE: {URL}")
        
        try:
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5)
            content = await page.content()
            
            # TRICK: Wir schneiden alles vor "Wetter aktuell" weg
            start_marker = "Wetter aktuell"
            if start_marker in content:
                # Wir nehmen nur den Teil NACH dem Marker
                parts = content.split(start_marker)
                relevant_content = parts[1] 
                print("Anker 'Wetter aktuell' gefunden. Filter aktiv.")
            else:
                relevant_content = content
                print("Anker nicht gefunden, nutze gesamten Quelltext (Vorsicht: evtl. ungenau).")

            # Suche nach Temperaturen im gefilterten Bereich
            # Muster: class="temperature"> gefolgt von der Zahl
            temps = re.findall(r'class="temperature"[^>]*>\s*(\-?\d+)', relevant_content)

            if len(temps) >= 16:
                print(f"ERFOLG: {len(temps)} stündliche Werte gefunden.")
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                client.loop_start()
                
                # Wir ordnen die Werte ab der aktuellen Stunde zu
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
                print(f"Zu wenig relevante Temperaturen gefunden ({len(temps)}).")
                
        except Exception as e:
            print(f"FEHLER: {e}")
        
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Minuten bis zum nächsten Scan...")
        time.sleep(1800)
