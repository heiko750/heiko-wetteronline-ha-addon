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
            await page.set_viewport_size({"width": 1280, "height": 3000})
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            
            # BANNER-KILLER & SCROLLEN
            await page.evaluate("() => { document.querySelectorAll('iframe, [id*=\"sp_message\"]').forEach(el => el.remove()); }")
            await page.mouse.wheel(0, 2000) 
            await asyncio.sleep(10) 
            
            # JAVASCRIPT-EXTRAKTION MIT ANKER
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

                    // Wir suchen den Bereich, der die STÜNDLICHE Vorhersage enthält
                    // Alles vor dem Wort "Stündlich" im Textinhalt wird ignoriert
                    const bodyText = document.body.innerText;
                    const hourlyIndex = bodyText.indexOf("Stündlich");
                    
                    const temps = findInShadow(document, '.temperature')
                        .filter(el => {
                            // Nur Temperaturen nehmen, die NACH dem Wort "Stündlich" im DOM kommen
                            return el.compareDocumentPosition(document.body) & Node.DOCUMENT_POSITION_PRECEDING;
                        })
                        .map(el => el.textContent.trim().replace(/[^0-9-]/g, ''))
                        .filter(txt => txt !== '');
                        
                    return { temps };
                }
            """)

            if data['temps']:
                # FALLBACK: Falls der DOM-Filter zu komplex ist, nehmen wir die Liste 
                # und ueberspringen die ersten 14 Werte (den 14-Tage Trend)
                real_temps = data['temps'][14:] if len(data['temps']) > 30 else data['temps']
                
                print(f"ERFOLG: {len(real_temps)} echte Stundenwerte nach Filter!")
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                client.loop_start()
                
                start_hour = datetime.now().hour
                for i in range(min(len(real_temps), 24)):
                    current_h = (start_hour + i) % 24
                    h_name = f"{current_h:02d}:00"
                    h_id = f"{current_h:02d}00"
                    t_val = real_temps[i]
                    
                    send_discovery(h_id, h_name)
                    client.publish(f"wetteronline/hourly/{h_id}/temp", t_val, retain=True)
                    print(f"Gelesen -> {h_name}: {t_val}°C")
                
                client.loop_stop()
                client.disconnect()
                
                # Wir nehmen jetzt bis zu 24 Paare
                limit = min(len(data['hours']), len(data['temps']), 24)
                for i in range(limit):
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
                print(f"Daten unvollständig: {len(data['hours'])}h / {len(data['temps'])}t")


        except Exception as e:
            print(f"FEHLER: {e}")
            
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Minuten bis zum nächsten Scan...")
        time.sleep(1800)
