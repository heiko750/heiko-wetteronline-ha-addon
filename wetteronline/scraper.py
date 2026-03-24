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
        browser = await p.chromium.launch(
            executable_path="/usr/bin/chromium", 
            headless=True, 
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            viewport={"width": 1280, "height": 3000}
        )
        
        # Cookie setzen (Zustimmung simulieren)
        await context.add_cookies([{"name": "euconsent-v2", "value": "CP-X", "domain": ".wetteronline.de", "path": "/"}])
        
        page = await context.new_page()
        print(f"STARTE ABFRAGE: {URL}")
        
        try:
            # Wir warten nur bis das Grundgeruest steht
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            
            # BANNER-KILLER: Wir loeschen alle moeglichen Werbe-Overlays per JS
            await page.evaluate("() => { document.querySelectorAll('iframe, [class*=\"sp-message\"], [id*=\"sp_message\"]').forEach(el => el.remove()); }")
            
            print("Warte auf Shadow-DOM Elemente...")
            # Hoeherer Timeout fuer den ODROID
            await page.wait_for_selector(".temperature", state="attached", timeout=60000)
            await asyncio.sleep(10) # Zeit zum "Atmen" fuer die CPU
            
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
                        .filter(txt => /^\\d{2}:00$/.test(txt));
                    
                    const temps = findInShadow(document, '.temperature')
                        .map(el => el.textContent.trim().replace(/[^0-9-]/g, ''))
                        .filter(txt => txt !== '');
                        
                    return { hours, temps };
                }
            """)

            if data['hours'] and data['temps']:
                print(f"ERFOLG: {len(data['temps'])} Temperaturen gefunden!")
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                client.loop_start()
                
                # Jetzt mit Range 24 fuer den vollen Tag
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
                print(f"Daten unvollstaendig: {len(data['hours'])}h / {len(data['temps'])}t")

        except Exception as e:
            print(f"FEHLER: {e}")
            
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Minuten bis zum nächsten Scan...")
        time.sleep(1800)
