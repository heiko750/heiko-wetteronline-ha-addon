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
        "icon": icon,
        "device_class": "temperature" if sensor_type == "temp" else None,
        "unit_of_measurement": unit if unit else None
    }
    client.publish(topic, json.dumps(payload), retain=True)

async def scrape():
    async with async_playwright() as p:
        # Browser mit explizitem Pfad für HA-Addon
        browser = await p.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox", "--disable-gpu"])
        context = await browser.new_context(viewport={"width": 1280, "height": 3000})
        page = await context.new_page()
        
        print(f"STARTE SCAN: {URL}")
        try:
            # 1. Seite laden
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5)

            # 2. Cookie-Banner wegschalten (verschiedene Methoden)
            try:
                # Wir suchen Buttons mit Text "Akzeptieren" oder "Zustimmen"
                accept_btn = page.get_by_role("button", name=re.compile(r"Akzeptieren|Zustimmen|Alle akzeptieren", re.IGNORECASE))
                if await accept_btn.count() > 0:
                    print("Cookie-Banner erkannt. Klicke 'Akzeptieren'...")
                    await accept_btn.first.click()
                    await asyncio.sleep(2)
            except: pass

            # 3. Pfeil-Button für die 24h-Ansicht finden
            # WetterOnline nutzt oft ein Element mit einem SVG-Pfeil nach rechts
            # Wir probieren erst den klassischen CSS-Weg, dann eine Suche nach dem Icon
            arrow = page.locator(".hourly-forecast-container .arrow-right, .forecast-hourly .arrow-right, [class*='arrow-right']").first
            
            if await arrow.count() == 0:
                # Fallback: Suche nach dem SVG oder einem Button im Stunden-Bereich
                arrow = page.locator("div[class*='hourly'] .arrow-right, div[class*='hourly'] svg").last

            if await arrow.count() > 0:
                print("Stunden-Pfeil gefunden. Starte 17 Klicks für 24h-Daten...")
                for k in range(17):
                    try:
                        if await arrow.is_visible():
                            await arrow.click()
                            await asyncio.sleep(0.5)
                    except: break
                print("Klicks beendet.")
            else:
                print("HINWEIS: Kein Pfeil gefunden. Versuche Daten direkt zu lesen.")

            # 4. Daten auslesen
            # Wir suchen jetzt breiter nach den Stunden-Items
            data = await page.evaluate("""
                () => {
                    const results = [];
                    // Wir suchen alle Elemente, die nach Uhrzeit (XX:00) aussehen
                    const allElements = Array.from(document.querySelectorAll('*'));
                    const hourBlocks = allElements.filter(el => {
                        const txt = el.textContent?.trim() || "";
                        return /^[0-2][0-9]:00$/.test(txt) && el.children.length === 0;
                    }).map(el => el.closest('div, wo-forecast-hour, .forecast-hour, .hourly-forecast-item')).filter(Boolean);

                    // Dubletten entfernen (nach Stunden-Text)
                    const uniqueBlocks = [];
                    const seenHours = new Set();
                    
                    hourBlocks.forEach(b => {
                        const h = b.innerText.match(/[0-2][0-9]:00/)?.[0];
                        if (h && !seenHours.has(h)) {
                            seenHours.add(h);
                            uniqueBlocks.push(b);
                        }
                    });

                    uniqueBlocks.forEach(b => {
                        const h = b.innerText.match(/[0-2][0-9]:00/)?.[0];
                        // Temperatur finden: Erste Zahl im Block, die nicht die Uhrzeit ist
                        const tempMatch = b.innerText.match(/(-?\\d+)°/);
                        const t = tempMatch ? tempMatch[1] : null;
                        
                        // Condition (Icon-Alt-Text)
                        const c = b.querySelector('img')?.getAttribute('alt')?.trim() || "Unbekannt";
                        
                        // Wind
                        let w = "Ruhig";
                        if (b.innerHTML.includes('ic_heavy_wind')) w = "Sturm";
                        else if (b.innerHTML.includes('ic_wind')) w = "Windig";

                        if (h && t) {
                            results.push({hour: h, temp: t, condition: c, wind: w});
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

                for entry in data[:24]:
                    h_id = entry['hour'].replace(":", "")
                    send_discovery(h_id, entry['hour'], "temp", "°C", "mdi:thermometer")
                    send_discovery(h_id, entry['hour'], "condition", None, "mdi:weather-partly-cloudy")
                    send_discovery(h_id, entry['hour'], "wind", None, "mdi:weather-windy")
                    
                    client.publish(f"wetteronline/hourly/{h_id}/temp", entry['temp'], retain=True)
                    client.publish(f"wetteronline/hourly/{h_id}/condition", entry['condition'], retain=True)
                    client.publish(f"wetteronline/hourly/{h_id}/wind", entry['wind'], retain=True)
                
                time.sleep(2)
                client.loop_stop(); client.disconnect()
            else:
                print("FEHLER: Keine Daten extrahiert. Screenshot erstellt.")
                await page.screenshot(path="/usr/src/app/debug_error.png")

        except Exception as e:
            print(f"KRITISCHER FEHLER: {e}")
            
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Min...")
        time.sleep(1800)
