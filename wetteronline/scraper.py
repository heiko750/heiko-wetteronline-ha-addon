import asyncio, re, json, time, os
from playwright.async_api import async_playwright
import paho.mqtt.client as mqtt

# --- KONFIGURATION ---
MQTT_HOST = "core-mosquitto"
MQTT_USER = os.getenv("MQTT_USER", "mqtt-user")
MQTT_PASS = os.getenv("MQTT_PASS")
LOCATION = os.getenv("LOCATION", "grafing")
URL = f"https://www.wetteronline.de/wetter/{LOCATION.strip('/')}"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

def send_discovery(h_id, h_name):
    topic = f"homeassistant/sensor/wo_{h_id}_temp/config"
    payload = {
        "name": f"WO {h_name} Temp",
        "state_topic": f"wetteronline/hourly/{h_id}/temp",
        "unique_id": f"wo_temp_{h_id}",
        "unit_of_measurement": "°C",
        "device_class": "temperature",
        "icon": "mdi:thermometer"
    }
    client.publish(topic, json.dumps(payload), retain=True)

async def scrape():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1280, "height": 2000})
        page = await context.new_page()
        
        print(f"STARTE ULTRA-SCAN: {URL}")
        try:
            await page.goto(URL, timeout=60000, wait_until="load")
            await asyncio.sleep(8) # Warten auf JS-Inhalte

            # 1. Cookie-Banner "blind" wegdrücken (Eingabetaste simulieren)
            await page.keyboard.press("Escape")
            await asyncio.sleep(2)

            # 2. Den Pfeil-Button suchen (wir suchen jetzt nach JEDEM Element, das klickbar ist und rechts liegt)
            # Wir nutzen JavaScript, um den Pfeil im Karussell zu finden
            print("Suche Stunden-Pfeil...")
            for _ in range(17):
                clicked = await page.evaluate("""() => {
                    const arrow = document.querySelector('.arrow-right, [class*="arrow-right"], .hourly-forecast-container .arrow');
                    if (arrow) { arrow.click(); return true; }
                    return false;
                }""")
                if not clicked: break
                await asyncio.sleep(0.5)

            # 3. Datenextraktion über Textanalyse (extrem robust)
            data = await page.evaluate("""() => {
                const results = [];
                // Wir sammeln alles, was nach Uhrzeit aussieht
                const texts = Array.from(document.querySelectorAll('*'))
                    .filter(el => /^[0-2][0-9]:00$/.test(el.innerText?.trim()) && el.children.length === 0);

                texts.forEach(el => {
                    const hour = el.innerText.trim();
                    const container = el.closest('div, wo-forecast-hour, .forecast-hour');
                    if (container) {
                        // Suche die Temperatur (°C) in diesem Block
                        const tempMatch = container.innerText.match(/(-?\\d+)°/);
                        if (tempMatch && !results.find(r => r.hour === hour)) {
                            results.push({ hour: hour, temp: tempMatch[1] });
                        }
                    }
                });
                return results;
            }""")

            if data:
                print(f"ERFOLG: {len(data)} Stunden gefunden.")
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                client.loop_start()

                for entry in data[:24]:
                    h_id = entry['hour'].replace(":", "")
                    send_discovery(h_id, entry['hour'])
                    client.publish(f"wetteronline/hourly/{h_id}/temp", entry['temp'], retain=True)
                    print(f"MQTT -> {entry['hour']}: {entry['temp']}°C")
                
                time.sleep(2)
                client.loop_stop(); client.disconnect()
            else:
                print("FEHLER: Keine Daten im DOM gefunden. Screenshot zur Analyse folgt.")
                await page.screenshot(path="/usr/src/app/debug_final.png")

        except Exception as e:
            print(f"FEHLER: {e}")
            
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape()); time.sleep(1800)
