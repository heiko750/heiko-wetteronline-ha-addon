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
        context = await browser.new_context(viewport={"width": 1280, "height": 3000})
        page = await context.new_page()
        print(f"STARTE DEEP-SCAN (TEMP/WIND/WETTER): {URL}")
        try:
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            
            # Warte kurz, bis der Pfeil wirklich im HTML erscheint (max. 10 Sek)
            await page.wait_for_selector(".hourly-forecast-container .arrow-right", timeout=10000)

            arrow = page.locator(arrow_selector)

            # --- NEU: KLICK-SIMULATION FÜR DAS STUNDEN-KARUSSELL ---
            # Wir suchen den rechten Pfeil im Stunden-Container
            arrow_selector = ".hourly-forecast-container .arrow-right, .forecast-hourly .arrow-right"
            arrow = page.locator(arrow_selector)
            
            if await arrow.count() > 0:
                print("Stunden-Karussell gefunden. Starte Klicks für 24h-Ansicht...")
                # 17 Klicks, um von 7 auf 24 Stunden zu kommen (1 Klick = 1 neue Stunde)
                for k in range(17):
                    if await arrow.is_visible():
                        await arrow.click()
                        # Kurze Pause für die Schiebe-Animation und das Nachladen der Daten
                        await asyncio.sleep(0.5) 
                print("Klicks abgeschlossen.")
            else:
                print("Hinweis: Pfeil-Button nicht gefunden. Scrape nur sichtbare Daten.")

            # DEEP-SCROLL (behalten wir bei, falls noch andere Seitenteile laden müssen)
            for i in range(2):
                await page.mouse.wheel(0, 800)
                await asyncio.sleep(2) 
            
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
                    // Wir erfassen alle Stunden-Blöcke, die nun im DOM vorhanden sind
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

                        if (h && h.includes(':00')) {
                            // Dubletten-Check: Nur hinzufügen, wenn diese Stunde noch nicht in der Liste ist
                            if (!results.find(item => item.hour === h)) {
                                results.push({hour: h, temp: t, condition: c, wind: w});
                            }
                        }
                    });
                    return results;
                }
            """)

            if data:
                print(f"ERFOLG: {len(data)} Stunden-Daten im Speicher.")
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                client.loop_start()
                
                # Wir sortieren nach Zeit, falls das Karussell die Reihenfolge im DOM gewürfelt hat
                # (Optional, aber sauberer)
                
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
            else:
                print("Keine Daten gefunden.")
                await page.screenshot(path="/usr/src/app/debug.png")
                
        except Exception as e: 
            print(f"FEHLER: {e}")
            await page.screenshot(path="/usr/src/app/debug.png")
            
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Min...")
        time.sleep(1800)
