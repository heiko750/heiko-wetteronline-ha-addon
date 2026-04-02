import asyncio, re, json, time, os
from datetime import datetime
from playwright.async_api import async_playwright
import paho.mqtt.client as mqtt

# --- KONFIGURATION ---
MQTT_HOST = "core-mosquitto"
MQTT_USER = os.getenv("MQTT_USER", "mqtt-user")
MQTT_PASS = os.getenv("MQTT_PASSWORD")
LOCATION = os.getenv("LOCATION", "grafing")
URL = f"https://wetteronline.de/wetter/{LOCATION.strip('/')}"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def send_discovery(h_id, h_name, sensor_type, unit, icon):
    topic = f"homeassistant/sensor/wo_{h_id}_{sensor_type}/config"
    payload = {
        "name": f"WO {h_name} {sensor_type.capitalize()}",
        "state_topic": f"wetteronline/hourly/{h_id}/{sensor_type}",
        "unique_id": f"wo_{sensor_type}_{h_id}",
        "icon": icon,
        "device_class": "temperature" if sensor_type == "temp" else None,
        "unit_of_measurement": unit if unit else None
    }
    client.publish(topic, json.dumps(payload), retain=True)

async def scrape():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox", "--disable-gpu"])
        context = await browser.new_context(viewport={"width": 1280, "height": 3000})
        page = await context.new_page()
        
        print(f"STARTE SCAN: {URL}")
        try:
            # 1. Seite laden (domcontentloaded ist schneller und stabiler bei Werbung)
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5) # Warten auf Scripte

            # 2. COOKIE-BANNER WEGKLICKEN (WICHTIG!)
            # Wir suchen nach dem typischen "Zustimmen" oder "Akzeptieren" Button
            cookie_selectors = ["button:has-text('Akzeptieren')", "button:has-text('Zustimmen')", ".cmp-button_accept"]
            for sel in cookie_selectors:
                btn = page.locator(sel)
                if await btn.count() > 0:
                    print("Cookie-Banner erkannt. Klicke 'Akzeptieren'...")
                    await btn.first.click()
                    await asyncio.sleep(2)
                    break

            # 3. PFEIL-BUTTON FINDEN UND 17x KLICKEN
            # Wir nutzen einen flexiblen Selektor fuer den rechten Pfeil
            arrow = page.locator(".hourly-forecast-container .arrow-right, .forecast-hourly .arrow-right, .arrow-right").first
            
            if await arrow.count() > 0:
                print("Stunden-Pfeil gefunden. Starte 17 Klicks für 24h-Daten...")
                for k in range(17):
                    if await arrow.is_visible():
                        await arrow.click()
                        await asyncio.sleep(0.6) # Animation abwarten
                print("Klicks beendet.")
            else:
                print("HINWEIS: Kein Pfeil gefunden. Scrape nur sichtbare Daten.")

            # 4. DATEN AUSLESEN PER EVALUATE
            data = await page.evaluate("""
                () => {
                    const results = [];
                    // Suche alle Stunden-Blöcke (auch die neu reingeschobenen)
                    const blocks = Array.from(document.querySelectorAll('wo-forecast-hour, .forecast-hour, .hourly-forecast-item'));
                    
                    blocks.forEach(b => {
                        const h = b.querySelector('wo-date-hour, .date-hour')?.textContent?.trim();
                        const t = b.querySelector('.temperature:not(.felt-temperature)')?.textContent?.trim().replace(/[^0-9-]/g, '');
                        const c = b.querySelector('img.symbol')?.getAttribute('alt')?.trim() || "Unbekannt";
                        
                        // Wind-Check
                        const images = Array.from(b.querySelectorAll('img'));
                        let w = "Ruhig";
                        images.forEach(img => {
                            const src = img.getAttribute('src') || "";
                            if (src.includes('ic_heavy_wind')) w = "Sturm";
                            else if (src.includes('ic_wind') && w !== "Sturm") w = "Windig";
                        });

                        if (h && h.includes(':00')) {
                            // Dubletten verhindern
                            if (!results.find(item => item.hour === h)) {
                                results.push({hour: h, temp: t, condition: c, wind: w});
                            }
                        }
                    });
                    return results;
                }
            """)

            if data:
                print(f"ERFOLG: {len(data)} Stunden gefunden.")
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                client.loop_start()

                # Sende bis zu 24 Stunden
                for entry in data[:24]:
                    h_id = entry['hour'].replace(":", "")
                    send_discovery(h_id, entry['hour'], "temp", "°C", "mdi:thermometer")
                    send_discovery(h_id, entry['hour'], "condition", None, "mdi:weather-partly-cloudy")
                    send_discovery(h_id, entry['hour'], "wind", None, "mdi:weather-windy")
                    
                    client.publish(f"wetteronline/hourly/{h_id}/temp", entry['temp'], retain=True)
                    client.publish(f"wetteronline/hourly/{h_id}/condition", entry['condition'], retain=True)
                    client.publish(f"wetteronline/hourly/{h_id}/wind", entry['wind'], retain=True)
                
                print(f"Daten für {min(len(data), 24)} Stunden an MQTT gesendet.")
                time.sleep(2)
                client.loop_stop(); client.disconnect()
            else:
                print("FEHLER: Keine Daten extrahiert.")
                await page.screenshot(path="/usr/src/app/debug_error.png")

        except Exception as e:
            print(f"KRITISCHER FEHLER: {e}")
            try: await page.screenshot(path="/usr/src/app/debug_crash.png")
            except: pass
            
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Min bis zum nächsten Scan...")
        time.sleep(1800)
