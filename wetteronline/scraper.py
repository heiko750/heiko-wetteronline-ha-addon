import asyncio
import re
import json
import time
import os
from datetime import datetime
from playwright.async_api import async_playwright
import paho.mqtt.client as mqtt

# --- KONFIGURATION ---
MQTT_HOST = "172.30.32.1"
MQTT_USER = os.getenv("MQTT_USER", "mqtt-user")
MQTT_PASS = os.getenv("MQTT_PASSWORD")
LOCATION = os.getenv("LOCATION", "grafing")

# Die URL muss hier definiert sein!
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
        # 1. Browser starten
        browser = await p.chromium.launch(
            executable_path="/usr/bin/chromium", 
            headless=True, 
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        
        # 2. Kontext erstellen (Hier werden Cookies und Viewport gesetzt)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 3000}
        )
        
        # 3. Cookie setzen, um den Banner zu umgehen
        await context.add_cookies([{
            "name": "euconsent-v2",
            "value": "CP-X",
            "domain": ".wetteronline.de",
            "path": "/"
        }])
        
        # 4. Seite im Kontext öffnen
        page = await context.new_page()
        print(f"STARTE ABFRAGE: {URL}")
        
        try:
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            print("Warte auf Shadow-DOM Rendering...")
            await page.wait_for_selector(".temperature", state="attached", timeout=30000)
            await asyncio.sleep(5) 
            
            # Dieser JavaScript-Block findet JEDES Element, auch in Shadow-Roots
            data = await page.evaluate("""
                () => {
                    const findInShadow = (root, selector) => {
                        let found = Array.from(root.querySelectorAll(selector));
                        root.querySelectorAll('*').forEach(el => {
                            if (el.shadowRoot) {
                                found = found.concat(findInShadow(el.shadowRoot, selector));
                            }
                        });
                        return found;
                    };

                    const hours = findInShadow(document, 'wo-date-hour, .date-hour')
                        .map(el => el.textContent.trim())
                        .filter(txt => /^\d{2}:00$/.test(txt));
                    
                    const temps = findInShadow(document, '.temperature')
                        .map(el => el.textContent.trim().replace(/[^0-9-]/g, ''))
                        .filter(txt => txt !== '');
                        
                    return { hours, temps };
                }
            """)

            if data['hours'] and data['temps']:
                print(f"ERFOLG: {len(data['temps'])} Temperaturen aus Shadow-DOM extrahiert!")
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                client.loop_start()
                
                # Wir nehmen die ersten 16 Paare
                for i in range(min(len(data['hours']), len(data['temps']), 24)):
                    h_name = data['hours'][i]
                    t_val = data['temps'][i]
                    h_id = h_name.replace(":", "")
                    
                    send_discovery(h_id, h_name)
                    client.publish(f"wetteronline/hourly/{h_id}/temp", t_val, retain=True)
                    print(f"Gelesen -> {h_name}: {t_val}°C")
                
                time.sleep(2)
                client.loop_stop()
                client.disconnect()
            else:
                print(f"Daten immer noch verborgen: {len(data['hours'])}h / {len(data['temps'])}t")

        except Exception as e:
            print(f"FEHLER: {e}")
            
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Minuten bis zum nächsten Scan...")
        time.sleep(1800)
