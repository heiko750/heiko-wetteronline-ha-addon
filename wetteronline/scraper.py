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
        # Kontext erstellen
        context = await browser.new_context(viewport={"width": 1280, "height": 5000})
        
        # DER TRICK: Wir setzen den "Zustimmungs-Status" manuell
        await context.add_cookies([{
            "name": "euconsent-v2",
            "value": "CP-X-NAP-X-NAAABAAAENAAAAAAA-AAAAAAA.YAAAAAAAAAAA",
            "domain": ".wetteronline.de",
            "path": "/"
        }])
        
        page = await context.new_page()
        print(f"STARTE MITTWOCHS-ABFRAGE: {URL}")
        
        try:
            # Seite laden
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            
            # BANNER-KILLER: Wir loeschen alle Overlays radikal per JavaScript
            await page.evaluate("""() => {
                document.querySelectorAll('iframe, [id*="sp_message"], [class*="sp-message"]').forEach(el => el.remove());
                document.body.style.overflow = 'visible';
            }""")
            
            print("Banner entfernt. Suche stündliche Daten...")
            await asyncio.sleep(10) 
            
            # Wir nutzen JavaScript, um die Daten direkt aus den Elementen zu ziehen
            # Das umgeht den fehleranfaelligen Quelltext-Scan
            data = await page.evaluate("""
                () => {
                    const results = [];
                    const nodes = document.querySelectorAll('wo-forecast-hour, .forecast-hour');
                    nodes.forEach(n => {
                        const h = n.querySelector('wo-date-hour, .date-hour')?.innerText;
                        const t = n.querySelector('.temperature')?.innerText;
                        if(h && t) results.push({h: h.trim(), t: t.replace('°','').trim()});
                    });
                    return results;
                }
            """)

            if data:
                print(f"ERFOLG: {len(data)} echte Stunden-Paare gefunden!")
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                client.loop_start()
                
                seen_hours = set()
                for entry in data:
                    h_name = entry['h']
                    t_val = entry['t']
                    if h_name not in seen_hours and len(seen_hours) < 24:
                        h_id = h_name.replace(":", "")
                        send_discovery(h_id, h_name)
                        client.publish(f"wetteronline/hourly/{h_id}/temp", t_val, retain=True)
                        print(f"Update -> {h_name}: {t_val}°C")
                        seen_hours.add(h_name)
                
                client.loop_stop()
                client.disconnect()
            else:
                print("Immer noch keine neuen Daten. Versuche Screenshot...")
                await page.screenshot(path="/usr/src/app/debug.png")

        except Exception as e:
            print(f"FEHLER: {e}")
        await browser.close()



if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Minuten...")
        time.sleep(1800)
