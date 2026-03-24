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
        browser = await p.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
        context = await browser.new_context(viewport={"width": 1280, "height": 3000})
        page = await context.new_page()
        print(f"STARTE ABFRAGE: {URL}")
        
        try:
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            # Wir loeschen Overlays, damit sie nicht stören
            await page.evaluate("() => { document.querySelectorAll('iframe, [id*=\"sp_message\"]').forEach(el => el.remove()); }")
            await page.mouse.wheel(0, 2000) 
            await asyncio.sleep(10) 
            
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

                    const results = [];
                    const blocks = findInShadow(document, 'wo-forecast-hour, .forecast-hour');
                    
                    blocks.forEach(b => {
                        const h_el = b.querySelector('wo-date-hour, .date-hour');
                        // Wir nehmen alle Temperatur-Divs im Block
                        const t_els = Array.from(b.querySelectorAll('.temperature'));
                        
                        // Wir filtern: Nur das Div, das NICHT 'felt-temperature' im Klassennamen hat
                        // Falls das nicht klappt, nehmen wir einfach das erste (Index 0)
                        const t_el = t_els.find(el => !el.classList.contains('felt-temperature')) || t_els[0];
                        
                        const h = h_el?.textContent?.trim();
                        const t = t_el?.textContent?.trim().replace(/[^0-9-]/g, '');
                        
                        if (h && h.includes(':00') && t) {
                            results.push({hour: h, temp: t});
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
                print("Keine Daten gefunden. Erstelle Screenshot zur Analyse...")
                await page.screenshot(path="/usr/src/app/debug.png")


        except Exception as e:
            print(f"FEHLER: {e}")
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Minuten...")
        time.sleep(1800)
