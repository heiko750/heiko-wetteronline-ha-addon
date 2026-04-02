import asyncio, re, json, time, os
from datetime import datetime
from playwright.async_api import async_playwright
import paho.mqtt.client as mqtt

# --- KONFIGURATION ---
MQTT_HOST = "core-mosquitto"
MQTT_USER = os.getenv("MQTT_USER", "mqtt-user")
MQTT_PASS = os.getenv("MQTT_PASSWORD")
LOCATION = os.getenv("LOCATION", "grafing")
URL = f"https://www.wetteronline.de/wetter/{LOCATION.strip('/')}"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def send_discovery(h_id, h_name, sensor_type, unit, icon):
    topic = f"homeassistant/sensor/wo_{h_id}_{sensor_type}/config"
    payload = {
        "name": f"WO {h_name} {sensor_type.capitalize()}",
        "state_topic": f"wetteronline/hourly/{h_id}/{sensor_type}",
        "unique_id": f"wo_{sensor_type}_{h_id}",
        "icon": icon
    }
    if unit: payload["unit_of_measurement"] = unit
    if sensor_type == "temp": payload["device_class"] = "temperature"
    client.publish(topic, json.dumps(payload), retain=True)

async def scrape():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox", "--disable-gpu"])
        # Wir setzen ein grosses Fenster (Viewport), um mehr Platz fuer die Tabelle zu haben
        context = await browser.new_context(viewport={"width": 1280, "height": 3000})
        page = await context.new_page()
        print(f"STARTE DEEP-SCAN (TEMP/WIND/WETTER): {URL}")
        try:
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            
            # DEEP-SCROLL: Wir "wecken" die Seite auf, um mehr Stunden zu laden
            for i in range(3):
                print(f"Scrolle Stufe {i+1}/3 für mehr Forecast-Daten...")
                await page.mouse.wheel(0, 1200)
                await asyncio.sleep(4) 
            
            data = await page.evaluate("""
                () => {
                    const findInShadow = (root, selector) => {
                        let found = Array.from(root.querySelectorAll(selector));
                        root.querySelectorAll('*').forEach(el => {
                            if (el.shadowRoot) found = found.concat(findInShadow(el.shadowRoot, selector));
                        });
                        return found;
                    };
                    const results = [];
                    const blocks = findInShadow(document, 'wo-forecast-hour, .forecast-hour');
                    blocks.forEach(b => {
                        const h = b.querySelector('wo-date-hour, .date-hour')?.textContent?.trim();
                        const t = b.querySelector('.temperature:not(.felt-temperature)')?.textContent?.trim().replace(/[^0-9-]/g, '');
                        const c = b.querySelector('img.symbol')?.getAttribute('alt')?.trim();
                        
                        const images = Array.from(b.querySelectorAll('img'));
                        let w = "Ruhig";
                        images.forEach(img => {
                            const src = img.getAttribute('src') || "";
                            if (src.includes('ic_heavy_wind')) { w = "Sturm"; }
                            else if (src.includes('ic_wind') && w !== "Sturm") { w = "Windig"; }
                        });

                        if (h && h.includes(':00')) results.push({hour: h, temp: t, condition: c, wind: w});
                    });
                    return results;
                }
            """)

            if data:
                print(f"ERFOLG: {len(data)} Stunden-Daten im Speicher.")
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                client.loop_start()
                # Wir nehmen jetzt bis zu 24 Stunden, falls vorhanden
                for entry in data[:24]:
                    h_id = entry['hour'].replace(":", "")
                    send_discovery(h_id, entry['hour'], "temp", "°C", "mdi:thermometer")
                    send_discovery(h_id, entry['hour'], "condition", None, "mdi:weather-partly-cloudy")
                    send_discovery(h_id, entry['hour'], "wind", None, "mdi:weather-windy")
                    
                    client.publish(f"wetteronline/hourly/{h_id}/temp", entry['temp'], retain=True)
                    client.publish(f"wetteronline/hourly/{h_id}/condition", entry['condition'], retain=True)
                    client.publish(f"wetteronline/hourly/{h_id}/wind", entry['wind'], retain=True)
                    print(f"MQTT -> {entry['hour']}: {entry['temp']}°C, {entry['condition']}, {entry['wind']}")
                time.sleep(2)
                client.loop_stop(); client.disconnect()
                await page.screenshot(path="/usr/src/app/debug.png")
                print("Screenshot debug.png erstellt for debugging")
            else:
                # Debug: Screenshot wenn nichts gefunden wird
                await page.screenshot(path="/usr/src/app/debug.png")
                print("Keine Daten gefunden - Screenshot debug.png erstellt.")
        except Exception as e: print(f"FEHLER: {e}")
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape()); print("Warte 30 Min..."); time.sleep(1800)
