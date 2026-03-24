import asyncio
import re
import json
import time
import base64
from datetime import datetime
from playwright.async_api import async_playwright
import paho.mqtt.client as mqtt

URL = base64.b64decode("aHR0cHM6Ly93d3cud2V0dGVyb25saW5lLmRlL3dldHRlci9ncmFmaW5n").decode('utf-8')
MQTT_HOST = "172.30.32.1"
MQTT_USER = "mqtt-user"
MQTT_PASS = "xxx" # Dein Passwort

async def scrape():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/chromium", headless=True, args=["--no-sandbox"])
        page = await browser.new_page()
        print(f"Abfrage läuft: {URL}")
        try:
            await page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            content = await page.content()
            
            # Wir extrahieren nur die 16 echten Temperaturen
            temps = re.findall(r'(\-?\d+)°', content)

            if len(temps) >= 16:
                print(f"Erfolg: {len(temps)} Temperaturen gefunden!")
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
                client.username_pw_set(MQTT_USER, MQTT_PASS)
                client.connect(MQTT_HOST, 1883, 60)
                
                # Wir bestimmen die aktuelle Stunde als Startpunkt
                start_hour = datetime.now().hour
                
                for i in range(16):
                    current_h = (start_hour + i) % 24
                    h_name = f"{current_h:02d}:00"
                    h_id = f"{current_h:02d}00"
                    t_val = temps[i]
                    
                    # Discovery & State
                    topic = f"homeassistant/sensor/wo_{h_id}/config"
                    client.publish(topic, json.dumps({
                        "name": f"WO {h_name}", 
                        "state_topic": f"wetteronline/hourly/{h_id}/temp", 
                        "unit_of_measurement": "°C", 
                        "unique_id": f"wo_t_{h_id}",
                        "device_class": "temperature"
                    }), retain=True)
                    
                    client.publish(f"wetteronline/hourly/{h_id}/temp", t_val, retain=True)
                    print(f"MQTT -> {h_name}: {t_val}°C")
                
                client.disconnect()
            else:
                print(f"Zu wenig Daten im Quelltext ({len(temps)}).")
        except Exception as e:
            print(f"FEHLER: {e}")
        await browser.close()

if __name__ == "__main__":
    while True:
        asyncio.run(scrape())
        print("Warte 30 Min...")
        time.sleep(1800)
