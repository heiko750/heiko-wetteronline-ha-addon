import asyncio
from playwright.async_api import async_playwright
import paho.mqtt.client as mqtt
import json
import os

MQTT_HOST = os.getenv("MQTT_HOST", "core-mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
LOCATION = os.getenv("LOCATION", "grafing")

URL = f"https://www.wetteronline.de/wetter/{LOCATION}"

client = mqtt.Client()
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
    config_icon = {
        "name": f"WetterOnline Icon {hour}",
        "state_topic": f"wetteronline/hourly/{hour}/icon",
        "unique_id": f"wo_icon_{hour}"
    }

    client.publish(f"{base}_temp/config", json.dumps(config_temp), retain=True)
    client.publish(f"{base}_icon/config", json.dumps(config_icon), retain=True)

async def scrape():
    async with async_playwright() as p:
        # Pfad zum System-Chromium (unter Debian meist /usr/bin/chromium)
        browser_path = os.getenv("PLAYWRIGHT_CHROME_EXECUTABLE_PATH", "/usr/bin/chromium")
        browser = await p.chromium.launch(
            executable_path=browser_path,
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        page = await browser.new_page()

        await page.goto(URL, timeout=60000)

        hours = page.locator("wo-forecast-hour")
        count = await hours.count()

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
            # Neue Bestätigungszeile für das Log:
            print(f"MQTT gesendet: {hour_text} Uhr -> {temp_text}°C (Icon: {icon_attr})")

        await asyncio.sleep(2)
        await browser.close()
        print("Scrape-Vorgang abgeschlossen.") # Abschlussmeldung

if __name__ == "__main__":
    asyncio.run(scrape())
