import os
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

# Import integrations
from integrations.outlook_calendar import OutlookCalendar
from integrations.google_calendar import GoogleCalendar
from integrations.notifiers.webhook import WebhookNotifier
from integrations.notifiers.mqtt import MQTTNotifier
from integrations.notifiers.rest_api import RESTAPIServer


class IntegrationManager:
    """Manages all calendar and notification integrations"""

    def __init__(self):
        load_dotenv()
        self.calendars = []
        self.notifiers = []
        self.rest_api = None
        self._initialize_integrations()

    def _initialize_integrations(self):
        """Initialize enabled integrations based on .env"""

        # Outlook Calendar (backward compatibility)
        if os.getenv("ENABLE_OUTLOOK", "true").lower() == "true":
            try:
                outlook = OutlookCalendar()
                self.calendars.append(("Outlook", outlook))
                print("[Integration] Outlook Calendar enabled")
            except Exception as e:
                print(f"[Integration] Outlook Calendar failed to initialize: {e}")

        # Google Calendar
        if os.getenv("ENABLE_GOOGLE_CALENDAR", "false").lower() == "true":
            try:
                service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "google_service_account.json")
                calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
                google = GoogleCalendar(service_account_file, calendar_id)
                self.calendars.append(("Google", google))
                print("[Integration] Google Calendar enabled")
            except Exception as e:
                print(f"[Integration] Google Calendar failed to initialize: {e}")

        # Home Assistant Webhook
        if os.getenv("ENABLE_HA_WEBHOOK", "false").lower() == "true":
            try:
                webhook_url = os.getenv("HA_WEBHOOK_URL")
                if webhook_url:
                    webhook = WebhookNotifier(webhook_url)
                    self.notifiers.append(("Webhook", webhook))
                    print("[Integration] HA Webhook enabled")
            except Exception as e:
                print(f"[Integration] HA Webhook failed to initialize: {e}")

        # MQTT
        if os.getenv("ENABLE_MQTT", "false").lower() == "true":
            try:
                mqtt_broker = os.getenv("MQTT_BROKER")
                if mqtt_broker:
                    mqtt_notifier = MQTTNotifier(
                        broker=mqtt_broker,
                        port=int(os.getenv("MQTT_PORT", "1883")),
                        username=os.getenv("MQTT_USERNAME"),
                        password=os.getenv("MQTT_PASSWORD"),
                        topic=os.getenv("MQTT_TOPIC", "homeassistant/sensor/blackbin")
                    )
                    self.notifiers.append(("MQTT", mqtt_notifier))
                    print("[Integration] MQTT enabled")
            except Exception as e:
                print(f"[Integration] MQTT failed to initialize: {e}")

        # REST API
        if os.getenv("ENABLE_REST_API", "false").lower() == "true":
            try:
                self.rest_api = RESTAPIServer(
                    host=os.getenv("REST_API_HOST", "0.0.0.0"),
                    port=int(os.getenv("REST_API_PORT", "5000"))
                )
                self.rest_api.start()
                print("[Integration] REST API enabled")
            except Exception as e:
                print(f"[Integration] REST API failed to initialize: {e}")

    def create_calendar_events(self, title: str, start: datetime, end: datetime, location: str = None):
        """Create events in all enabled calendars"""
        print(f"\n=== Creating calendar events for {start.strftime('%Y-%m-%d')} ===")

        for name, calendar in self.calendars:
            try:
                calendar.create_event(title, start, end, location)
            except Exception as e:
                print(f"[{name}] Error creating event: {e}")

    def send_notifications(self, title: str, date: datetime):
        """Send notifications via all enabled notifiers"""
        print(f"\n=== Sending notifications ===")

        for name, notifier in self.notifiers:
            try:
                notifier.notify(title, date)
            except Exception as e:
                print(f"[{name}] Error sending notification: {e}")

        # Update REST API
        if self.rest_api:
            try:
                self.rest_api.update_date(date)
            except Exception as e:
                print(f"[REST API] Error updating date: {e}")


class BlackBin:
    def __init__(self):
        load_dotenv()
        client_id = os.getenv("CLIENT_ID")
        client_secret = os.getenv("CLIENT_SECRET")
        self.credentials = (client_id, client_secret)
        self.options = webdriver.ChromeOptions()
        self.options.add_argument("--disable-dev-shm-usage")
        self.options.add_argument("--disable-extensions")
        self.options.add_argument("--disable-gpu")
        self.options.add_argument("--headless")
        self.options.add_experimental_option("excludeSwitches", ['enable-automation'])
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
                     "(KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
        self.options.add_argument('--user-agent={}'.format(user_agent))
        self.url = "https://online.belfastcity.gov.uk/find-bin-collection-day/Default.aspx"
        self.year = int()
        self.month = int()
        self.day = int()
        self.integration_manager = IntegrationManager()

    def start_chrome(self):
        selenium_host = os.getenv("SELENIUM_HOST", "localhost")
        selenium_port = os.getenv("SELENIUM_PORT", "4444")
        selenium_url = f"http://{selenium_host}:{selenium_port}/wd/hub"
        retries = 5
        for i in range(retries):
            try:
                self.driver = webdriver.Remote(selenium_url, options=self.options)
                print(f"Successfully connected to Selenium server at {selenium_url}.")
                return
            except Exception as e:
                print(f"Attempt {i+1}/{retries} to connect to Selenium server at {selenium_url} failed: {e}")
                time.sleep(2 ** i)
        raise Exception("Failed to connect to Selenium server after multiple retries.")

    def get_bin(self, house_address):
        house_address = house_address.upper()
        postcode = house_address.split(', ')[2]
        self.driver.get(self.url)
        time.sleep(1)
        WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "label[for='searchBy_radio_1']"))).click()
        WebDriverWait(self.driver, 10).until(EC.presence_of_element_located((By.ID, "Postcode_textbox"))).send_keys(postcode)
        self.driver.find_element(By.ID, "AddressLookup_button").click()
        select = Select(self.driver.find_element(By.ID, "lstAddresses"))
        try:
            select.select_by_visible_text(house_address)
            self.driver.find_element(By.ID, "SelectAddress_button").click()
            try:
                table = self.driver.find_element(By.ID, "ItemsGrid").find_elements(By.TAG_NAME, "tr")[1].text
                table = table.split(' ')
                del table[:3]
                month = table[3]
                months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                if month in months:
                    self.month = months.index(month) + 1
                self.day = int(table[4])
                self.year = int(table[5])
                print(f"Scraped bin collection date: {self.year}-{self.month:02d}-{self.day:02d}")
            except NoSuchElementException:
                print("The Information is Missing From Belfast City Council Website")
                info = self.driver.find_element(By.ID, "BinDetailsPnl").text
                print(info)
                self.get_exit()
                quit()
        except NoSuchElementException:
            print("The Address Is Incorrect!")
            print(house_address)
            self.get_exit()
            quit()

    def get_exit(self):
        self.driver.quit()

    def update_all_integrations(self):
        """Update all calendars and send all notifications"""
        if not all([self.year, self.month, self.day]):
            print("No valid bin collection date found. Skipping integrations.")
            return

        collection_start = datetime(self.year, self.month, self.day, 0, 0)
        collection_end = collection_start + timedelta(days=1)

        # Create calendar events
        self.integration_manager.create_calendar_events(
            title="Bin collection",
            start=collection_start,
            end=collection_end,
            location="Belfast"
        )

        # Send notifications
        self.integration_manager.send_notifications(
            title="Bin collection",
            date=collection_start
        )

        print("\n=== Integration update complete ===")


if __name__ == '__main__':
    load_dotenv()
    house = os.getenv("HOUSE_ADDRESS")
    bins = BlackBin()
    bins.start_chrome()
    bins.get_bin(house)
    bins.get_exit()
    bins.update_all_integrations()
