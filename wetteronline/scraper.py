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
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            await page.evaluate("() => { document.querySelectorAll('iframe, [id*=\"sp_message\"]').forEach(el => el.remove()); }")
            
            # DER SCROLL-TRICK: Einmal 2000 Pixel nach unten fuer mehr Daten
            print("Simuliere Scrollen für die Mittagswerte...")
            await page.mouse.wheel(0, 2000) 
            await asyncio.sleep(10)
            
            # 2. Banner-Killer
            await page.evaluate("() => { document.querySelectorAll('iframe, [id*=\"sp_message\"]').forEach(el => el.remove()); }")
            print("Warte auf Shadow-DOM Inhalte...")
            await asyncio.sleep(15) 

            # 3. SHADOW-DOM BYPASS (Der entscheidende Teil)
            data = await page.evaluate("""
                () => {
                    const results = [];
                    // Diese Funktion taucht tief in die versteckten Shadow-Roots ab
                    const findInShadow = (root, selector) => {
                        let found = Array.from(root.querySelectorAll(selector));
                        root.querySelectorAll('*').forEach(el => {
                            if (el.shadowRoot) {
                                found = found.concat(findInShadow(el.shadowRoot, selector));
                            }
                        });
                        return found;
                    };

                    const blocks = findInShadow(document, 'wo-forecast-hour, .forecast-hour');
                    blocks.forEach(b => {
                        const h = b.querySelector('wo-date-hour, .date-hour')?.textContent;
                        const t = b.querySelector('.temperature')?.textContent;
                        if (h && t) {
                            results.push({
                                hour: h.trim(), 
                                temp: t.trim().replace(/[^0-9-]/g, '')
                            });
                        }
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
                    h_name = entry['hour']
                    t_val = entry['temp']
                    if h_name not in seen_hours and len(seen_hours) < 24:
                        h_id = h_name.replace(":", "")
                        send_discovery(h_id, h_name)
                        client.publish(f"wetteronline/hourly/{h_id}/temp", t_val, retain=True)
                        print(f"Gelesen -> {h_name}: {t_val}°C")
                        seen_hours.add(h_name)
                
                time.sleep(2)
                client.loop_stop()
                client.disconnect()
            else:
                print("Daten immer noch im Shadow-DOM gesperrt.")

        except Exception as e:
            print(f"FEHLER: {e}")

        await browser.close()



if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Minuten...")
        time.sleep(1800)
