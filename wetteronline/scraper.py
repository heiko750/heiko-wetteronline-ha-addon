import asyncio
import time
from playwright.async_api import async_playwright
import paho.mqtt.client as mqtt
import json
import os

# Konfiguration
MQTT_HOST = os.getenv("MQTT_HOST", "core-mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
LOCATION = os.getenv("LOCATION", "grafing")
INTERVAL = int(os.getenv("INTERVAL", "30")) # Hier war der Fehler!

URL = f"https://www.wetteronline.de{LOCATION}"

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(MQTT_HOST, MQTT_PORT, 60)

published_discovery = set()

def publish_discovery(hour):
    if hour in published_discovery:
        return
    published_discovery.add(hour)
    base = f"homeassistant/sensor/wetteronline_{hour}"
    
    config_temp = {
        "name": f"WetterOnline Temperatur {hour}",
        "state_topic": f"wetteronline/hourly/{hour}/temp",
        "unit_of_measurement": "°C",
        "unique_id": f"wo_temp_{hour}"
    }
    client.publish(f"{base}_temp/config", json.dumps(config_temp), retain=True)

async def scrape():
    async with async_playwright() as p:
        browser_path = os.getenv("PLAYWRIGHT_CHROME_EXECUTABLE_PATH", "/usr/bin/chromium")
        browser = await p.chromium.launch(
            executable_path=browser_path,
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page()

        print(f"Rufe URL auf: {URL}")
        await page.goto(URL, timeout=60000, wait_until="networkidle")
        
        # 1. Cookie-Banner im Iframe wegklicken
        try:
            print("Suche nach Cookie-Banner...")
            # Sourcepoint Iframe-Selektor
            iframe_element = page.frame_locator('iframe[title*="SP Consent Message"]')
            accept_button = iframe_element.get_by_role("button", name="ALLES AKZEPTIEREN")
            await accept_button.click(timeout=10000)
            print("Cookie-Banner erfolgreich bestätigt.")
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Kein Banner gefunden oder Fehler beim Klicken: {e}")

        # 2. Wetterdaten suchen
        try:
            await page.wait_for_selector("wo-forecast-hour", timeout=15000)
            hours = page.locator("wo-forecast-hour")
            count = await hours.count()
            print(f"Gefundene Stunden-Elemente: {count}")

            for i in range(count):
                h = hours.nth(i)
                hour_el = h.locator("wo-date-hour")
                temp_el = h.locator("wo-temperature .temperature")
                icon_el = h.locator("wo-icon")

                if await hour_el.count() == 0:
                    continue

                hour_text = (await hour_el.inner_text()).strip()
                temp_text = (await temp_el.inner_text()).strip()
                icon_attr = await icon_el.get_attribute("data-icon")

                publish_discovery(hour_text)
                client.publish(f"wetteronline/hourly/{hour_text}/temp", temp_text, retain=True)
                client.publish(f"wetteronline/hourly/{hour_text}/icon", icon_attr, retain=True)
                print(f"MQTT gesendet: {hour_text} Uhr -> {temp_text}°C")

        except Exception as e:
            print(f"Fehler beim Scraping: {e}")
            await page.screenshot(path="/config/wetter_error.png")

        await browser.close()
        print("Scrape-Vorgang abgeschlossen.")

if __name__ == "__main__":
    while True:
        try:
            asyncio.run(scrape())
        except Exception as e:
            print(f"Kritischer Fehler in der Hauptschleife: {e}")
        
        print(f"Warte {INTERVAL} Minuten bis zum nächsten Scan...")
        time.sleep(INTERVAL * 60)
