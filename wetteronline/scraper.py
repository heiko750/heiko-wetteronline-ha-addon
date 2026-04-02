import asyncio, re, json, time, os
from playwright.async_api import async_playwright
import paho.mqtt.client as mqtt

# --- KONFIGURATION ---
MQTT_HOST = "core-mosquitto"
MQTT_USER = os.getenv("MQTT_USER", "mqtt-user")
MQTT_PASS = os.getenv("MQTT_PASS")
LOCATION = os.getenv("LOCATION", "grafing")
URL = f"https://wetteronline.de/wetter/{LOCATION.strip('/')}"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

async def scrape():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1280, "height": 2000})
        page = await context.new_page()
        
        print(f"STARTE SCAN (Grafing): {URL}")
        try:
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            await asyncio.sleep(5) 

            # --- 1. COOKIE-BANNER WEGKLICKEN (PRÄZISE) ---
            # Wir suchen exakt nach dem Text, den du auf dem Screenshot gesehen hast
            cookie_button = page.get_by_role("button", name=re.compile(r"Akzeptieren & Weiter", re.IGNORECASE))
            if await cookie_button.count() > 0:
                print("Cookie-Banner 'Akzeptieren & Weiter' gefunden. Klicke...")
                await cookie_button.first.click()
                await asyncio.sleep(3) # Warten, bis der Banner verschwindet
            else:
                # Fallback, falls es kein Button-Element ist
                await page.click("text=Akzeptieren & Weiter")
                await asyncio.sleep(3)

            # --- 2. 17x KLICKEN FÜR 24 STUNDEN ---
            print("Suche Stunden-Pfeil...")
            # Wir nutzen JS-Klick, falls CSS-Klick blockiert wird
            for i in range(17):
                clicked = await page.evaluate("""() => {
                    const arrow = document.querySelector('.arrow-right, [class*="arrow-right"]');
                    if (arrow) { arrow.click(); return true; }
                    return false;
                }""")
                if not clicked: break
                await asyncio.sleep(0.4)

            # --- 3. DATEN EXTRAHIEREN ---
            data = await page.evaluate("""() => {
                const results = [];
                const blocks = Array.from(document.querySelectorAll('wo-forecast-hour, .forecast-hour, .hourly-forecast-item'));
                blocks.forEach(b => {
                    const h = b.innerText.match(/[0-2][0-9]:00/)?.[0];
                    const tMatch = b.innerText.match(/(-?\\d+)°/);
                    if (h && tMatch && !results.find(r => r.hour === h)) {
                        results.push({ hour: h, temp: tMatch[1] });
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
                    # Discovery & Publish hier (gekürzt für Übersicht)
                    client.publish(f"wetteronline/hourly/{h_id}/temp", entry['temp'], retain=True)
                client.loop_stop(); client.disconnect()
            else:
                print("FEHLER: Keine Daten extrahiert. Speichere neuen Screenshot.")
                await page.screenshot(path="/usr/src/app/debug_after_cookie.png")

        except Exception as e:
            print(f"FEHLER: {e}")
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape()); time.sleep(1800)
