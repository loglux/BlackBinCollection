import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
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


DEFAULT_CONFIG_PATH = "/data/blackbin_config.json"
DEFAULT_SCHEDULES = [
    "30 19 * * 1,5,6",
    "30 3 * * 3",
]
_DAY_MAP = {
    "sun": "0",
    "sunday": "0",
    "mon": "1",
    "monday": "1",
    "tue": "2",
    "tues": "2",
    "tuesday": "2",
    "wed": "3",
    "weds": "3",
    "wednesday": "3",
    "thu": "4",
    "thur": "4",
    "thurs": "4",
    "thursday": "4",
    "fri": "5",
    "friday": "5",
    "sat": "6",
    "saturday": "6",
}


def _load_config(config_path: str) -> dict:
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return _sanitize_config(data)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        print(f"[Config] Invalid JSON in {config_path}: {exc}")
        return {}


def _save_config(config_path: str, config: dict) -> None:
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2, sort_keys=True)


def _sanitize_config(value):
    if isinstance(value, dict):
        return {key: _sanitize_config(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_sanitize_config(item) for item in value]
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned == "":
            return None
        if cleaned.lower() in ("none", "null"):
            return None
        return cleaned
    return value


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


def _sanitize_input(value: str) -> str:
    value = _ANSI_ESCAPE_RE.sub("", value)
    buffer = []
    for ch in value:
        if ch in ("\b", "\x7f"):
            if buffer:
                buffer.pop()
            continue
        buffer.append(ch)
    value = "".join(buffer)
    value = "".join(ch for ch in value if ch.isprintable())
    return value.strip()


def _confirm_value(value: str) -> bool:
    while True:
        raw = input(f"Use '{value}'? [Y/n]: ")
        response = _sanitize_input(raw).lower()
        if response in ("", "y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print("Please enter y or n.")


def _prompt_text(prompt: str, default: str = None, allow_empty: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        raw = input(f"{prompt}{suffix}: ")
        value = _sanitize_input(raw)
        if value:
            if raw != value:
                if not _confirm_value(value):
                    continue
            return value
        if default is not None and value == "":
            return default
        if allow_empty:
            return ""
        print("Value is required.")


def _prompt_bool(prompt: str, default: bool = False) -> bool:
    suffix = " [Y/n]" if default else " [y/N]"
    while True:
        value = _sanitize_input(input(f"{prompt}{suffix}: ")).lower()
        if not value:
            return default
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        print("Please enter y or n.")


def _prompt_int(prompt: str, default: int = None) -> int:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        raw = input(f"{prompt}{suffix}: ")
        value = _sanitize_input(raw)
        if value == "" and default is not None:
            return default
        match = re.search(r"\d+", value)
        if match:
            parsed = int(match.group(0))
            if raw != value:
                if not _confirm_value(str(parsed)):
                    continue
            return parsed
        print("Please enter a valid number.")


def _parse_time(value: str):
    cleaned = value.strip().lower().replace(".", ":")
    if ":" not in cleaned:
        return None
    parts = cleaned.split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _parse_day_tokens(tokens: list) -> str:
    if not tokens:
        return ""
    day_values = []
    for token in tokens:
        if token in ("daily", "everyday"):
            return "*"
        if token in ("weekday", "weekdays"):
            day_values.append("1-5")
            continue
        if token in ("weekend", "weekends"):
            day_values.append("0,6")
            continue
        if token in _DAY_MAP:
            day_values.append(_DAY_MAP[token])
            continue
        if token.isdigit():
            day_values.append(token)
            continue
        return ""
    unique = []
    for value in day_values:
        if value not in unique:
            unique.append(value)
    return ",".join(unique)


def _parse_human_schedule(value: str):
    raw = value.strip().lower()
    if not raw:
        return None
    tokens = [token for token in re.split(r"[,\s]+", raw) if token]
    if not tokens:
        return None
    if len(tokens) == 1:
        parsed_time = _parse_time(tokens[0])
        if parsed_time:
            hour, minute = parsed_time
            return f"{minute} {hour} * * *"
        return None

    parsed_time = _parse_time(tokens[-1])
    if not parsed_time:
        return None
    day_part = _parse_day_tokens(tokens[:-1])
    if not day_part:
        return None
    hour, minute = parsed_time
    return f"{minute} {hour} * * {day_part}"


def _prompt_cron_schedules(existing: list = None) -> list:
    if isinstance(existing, str):
        existing = [existing]

    if existing:
        if not _prompt_bool("Update schedule", default=False):
            return existing

    if _prompt_bool("Use default schedule (Mon/Fri/Sat 19:30, Wed 03:30)", default=True):
        return DEFAULT_SCHEDULES[:]

    schedules = []
    while True:
        line = _sanitize_input(
            input("Enter cron schedule (empty to finish, 'help' for examples): ")
        )
        if not line:
            if schedules:
                return schedules
            print("At least one schedule is required.")
            continue
        if line.lower() in ("help", "?"):
            print("Examples:")
            print("  30 3 * * 3")
            print("  mon,fri,sat 19:30")
            print("  wed 03:30")
            print("  3:30")
            continue
        if line.lower() in ("default", "defaults"):
            return DEFAULT_SCHEDULES[:]
        if line.lower() in ("cancel", "skip"):
            return existing or DEFAULT_SCHEDULES[:]

        if len(line.split()) >= 5:
            schedules.append(line)
            continue

        human = _parse_human_schedule(line)
        if human:
            schedules.append(human)
            continue

        print("Cron schedule must have at least 5 fields or a supported shortcut.")


def _resolve_address(config: dict) -> dict:
    address = config.get("address", {})
    postcode = address.get("postcode") or os.getenv("POSTCODE")
    address_id = address.get("address_id") or os.getenv("ADDRESS_ID")
    address_text = address.get("address_text") or os.getenv("ADDRESS_TEXT")

    if not postcode or not (address_id or address_text):
        return {}

    return {
        "postcode": postcode.strip(),
        "address_id": (str(address_id).strip() if address_id else None),
        "address_text": address_text.strip() if address_text else None,
    }


class IntegrationManager:
    """Manages all calendar and notification integrations"""

    def __init__(self, config: dict = None):
        load_dotenv()
        self.config = config or {}
        self._apply_config_env()
        self.calendars = []
        self.notifiers = []
        self.rest_api = None
        self._initialize_integrations()

    def _apply_config_env(self):
        calendars = self.config.get("calendars", {})
        outlook = calendars.get("outlook", {})
        google = calendars.get("google", {})

        if outlook.get("client_id"):
            os.environ["CLIENT_ID"] = outlook["client_id"]
        if outlook.get("client_secret"):
            os.environ["CLIENT_SECRET"] = outlook["client_secret"]
        if outlook.get("tenant_id"):
            os.environ["TENANT_ID"] = outlook["tenant_id"]
        if outlook.get("token_file"):
            os.environ["OUTLOOK_TOKEN_FILE"] = outlook["token_file"]
        if outlook.get("calendar_name"):
            os.environ["OUTLOOK_CALENDAR_NAME"] = outlook["calendar_name"]
        if outlook.get("calendar_id"):
            os.environ["OUTLOOK_CALENDAR_ID"] = outlook["calendar_id"]

        if google.get("service_account_file"):
            os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"] = google["service_account_file"]
        if google.get("calendar_id"):
            os.environ["GOOGLE_CALENDAR_ID"] = google["calendar_id"]

    def _initialize_integrations(self):
        """Initialize enabled integrations based on .env"""

        # Outlook Calendar (backward compatibility)
        outlook_config = self.config.get("calendars", {}).get("outlook", {})
        outlook_enabled = outlook_config.get("enabled")
        if outlook_enabled is None:
            outlook_enabled = os.getenv("ENABLE_OUTLOOK", "true").lower() == "true"

        if outlook_enabled:
            try:
                token_file = (
                    outlook_config.get("token_file")
                    or os.getenv("OUTLOOK_TOKEN_FILE")
                    or ("/data/o365_token.txt" if os.path.exists("/data/o365_token.txt") else None)
                    or "o365_token.txt"
                )
                calendar_name = (
                    outlook_config.get("calendar_name")
                    or os.getenv("OUTLOOK_CALENDAR_NAME")
                    or os.getenv("CALENDAR_NAME")
                )
                calendar_id = (
                    outlook_config.get("calendar_id")
                    or os.getenv("OUTLOOK_CALENDAR_ID")
                )
                outlook = OutlookCalendar(
                    token_file=token_file,
                    calendar_name=calendar_name,
                    calendar_id=calendar_id,
                )
                self.calendars.append(("Outlook", outlook))
                print("[Integration] Outlook Calendar enabled")
            except Exception as e:
                print(f"[Integration] Outlook Calendar failed to initialize: {e}")

        # Google Calendar
        google_config = self.config.get("calendars", {}).get("google", {})
        google_enabled = google_config.get("enabled")
        if google_enabled is None:
            google_enabled = os.getenv("ENABLE_GOOGLE_CALENDAR", "false").lower() == "true"

        if google_enabled:
            try:
                service_account_file = (
                    google_config.get("service_account_file")
                    or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "google_service_account.json")
                )
                calendar_id = google_config.get("calendar_id") or os.getenv("GOOGLE_CALENDAR_ID", "primary")
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
        mqtt_config = self.config.get("mqtt", {})
        mqtt_enabled = mqtt_config.get("enabled")
        if mqtt_enabled is None:
            mqtt_enabled = os.getenv("ENABLE_MQTT", "false").lower() == "true"

        if mqtt_enabled:
            try:
                mqtt_broker = mqtt_config.get("broker") or os.getenv("MQTT_BROKER")
                if mqtt_broker:
                    mqtt_notifier = MQTTNotifier(
                        broker=mqtt_broker,
                        port=int(mqtt_config.get("port") or os.getenv("MQTT_PORT", "1883")),
                        username=mqtt_config.get("username") or os.getenv("MQTT_USERNAME"),
                        password=mqtt_config.get("password") or os.getenv("MQTT_PASSWORD"),
                        topic=mqtt_config.get("topic") or os.getenv("MQTT_TOPIC", "homeassistant/sensor/blackbin"),
                        state_format=mqtt_config.get("state_format") or os.getenv("MQTT_STATE_FORMAT")
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
        print(f"\n=== Creating calendar events for {start.strftime('%a %Y-%m-%d')} ===")

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
    def __init__(self, config: dict = None, enable_integrations: bool = True):
        load_dotenv()
        self.config = config or {}
        self.last_error_message = None
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
        self.integration_manager = IntegrationManager(config=self.config) if enable_integrations else None

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

    def _navigate_to_postcode_search(self, postcode: str) -> Select:
        self.driver.get(self.url)
        time.sleep(1)
        WebDriverWait(self.driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "label[for='searchBy_radio_1']"))
        ).click()
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.ID, "Postcode_textbox"))
        ).send_keys(postcode)
        self.driver.find_element(By.ID, "AddressLookup_button").click()
        return Select(self.driver.find_element(By.ID, "lstAddresses"))

    def _extract_addresses(self, select: Select) -> list:
        addresses = []
        for option in select.options:
            text = (option.text or "").strip()
            value = (option.get_attribute("value") or "").strip()
            if not text or not value:
                continue
            if "select" in text.lower():
                continue
            addresses.append((value, text))
        return addresses

    def _wait_for_result_panel(self) -> str:
        def _panel_ready(driver):
            if driver.find_elements(By.ID, "ItemsGrid"):
                return "items"
            if driver.find_elements(By.ID, "BinDetailsPnl"):
                return "details"
            return False

        return WebDriverWait(self.driver, 10).until(_panel_ready)

    def configure(self, config_path: str) -> dict:
        if not sys.stdin.isatty():
            print("Interactive setup requires a TTY.")
            return {}

        config = _load_config(config_path)
        existing_address = config.get("address", {})
        existing_schedule = config.get("schedule", {}).get("cron")
        existing_mqtt = config.get("mqtt", {})

        postcode = _prompt_text("Postcode", default=existing_address.get("postcode"))
        select = self._navigate_to_postcode_search(postcode)
        addresses = self._extract_addresses(select)
        if not addresses:
            print("No addresses found. Check the postcode and try again.")
            return {}

        for idx, (_, text) in enumerate(addresses, start=1):
            print(f"{idx}. {text}")

        while True:
            choice = _prompt_text("Select address number")
            if choice.isdigit() and 1 <= int(choice) <= len(addresses):
                break
            print("Invalid selection.")

        address_id, address_text = addresses[int(choice) - 1]
        config["address"] = {
            "postcode": postcode,
            "address_id": address_id,
            "address_text": address_text,
        }

        config["schedule"] = {
            "cron": _prompt_cron_schedules(existing=existing_schedule),
        }

        if _prompt_bool("Configure MQTT", default=bool(existing_mqtt)):
            broker = _prompt_text("MQTT broker (empty to skip)", default=existing_mqtt.get("broker"), allow_empty=True)
            if not broker:
                if existing_mqtt:
                    if _prompt_bool("Keep existing MQTT config", default=True):
                        config["mqtt"] = existing_mqtt
                        _save_config(config_path, config)
                        print(f"Saved configuration to {config_path}")
                        return config
                config["mqtt"] = {"enabled": False}
                _save_config(config_path, config)
                print(f"Saved configuration to {config_path}")
                return config
            existing_port = existing_mqtt.get("port")
            port = _prompt_int("MQTT port", default=int(existing_port or 1883))
            username = _prompt_text("MQTT username", default=existing_mqtt.get("username"), allow_empty=True)
            password = _prompt_text("MQTT password", default=existing_mqtt.get("password"), allow_empty=True)
            topic = _prompt_text(
                "MQTT topic",
                default=existing_mqtt.get("topic") or "homeassistant/sensor/blackbin"
            )
            state_format = _prompt_text(
                "MQTT state date format (strftime, empty for YYYY-MM-DD)",
                default=existing_mqtt.get("state_format"),
                allow_empty=True
            )
            config["mqtt"] = {
                "enabled": True,
                "broker": broker,
                "port": port,
                "username": username or None,
                "password": password or None,
                "topic": topic,
                "state_format": state_format or None,
            }
        elif existing_mqtt:
            config["mqtt"] = existing_mqtt

        _save_config(config_path, config)
        print(f"Saved configuration to {config_path}")
        return config

    def get_bin(self, address: dict):
        self.last_error_message = None
        postcode = address.get("postcode")
        address_id = address.get("address_id")
        address_text = address.get("address_text")
        self.last_error_message = None
        if not postcode or not (address_id or address_text):
            print("Address configuration is missing.")
            self.last_error_message = "Address configuration is missing."
            return False

        select = self._navigate_to_postcode_search(postcode)
        try:
            if address_id:
                select.select_by_value(address_id)
            else:
                select.select_by_visible_text(address_text)

            self.driver.find_element(By.ID, "SelectAddress_button").click()
            try:
                panel = self._wait_for_result_panel()
            except TimeoutException:
                print("Timed out waiting for bin collection results.")
                self.last_error_message = "Timed out waiting for bin collection results."
                return False

            if panel == "details":
                print("The Information is Missing From Belfast City Council Website")
                try:
                    info = self.driver.find_element(By.ID, "BinDetailsPnl").text
                    print(info)
                    self.last_error_message = info.strip()
                except NoSuchElementException:
                    print("Bin details panel not found.")
                if not self.last_error_message:
                    self.last_error_message = "The Information is Missing From Belfast City Council Website."
                return False

            try:
                rows = self.driver.find_element(By.ID, "ItemsGrid").find_elements(By.TAG_NAME, "tr")
                if len(rows) < 2:
                    print("Bin collection table is missing expected rows.")
                    self.last_error_message = "Bin collection table is missing expected rows."
                    return False
                table = rows[1].text.split(' ')
                del table[:3]
                month = table[3]
                months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
                if month in months:
                    self.month = months.index(month) + 1
                self.day = int(table[4])
                self.year = int(table[5])
                collected = datetime(self.year, self.month, self.day)
                print(
                    "Scraped bin collection date: "
                    f"{collected.strftime('%Y-%m-%d')} ({collected.strftime('%a')})"
                )
                self.last_error_message = None
                return True
            except (NoSuchElementException, IndexError, ValueError):
                print("Failed to parse bin collection date from the results table.")
                self.last_error_message = "Failed to parse bin collection date from the results table."
                return False
        except NoSuchElementException:
            print("The Address Is Incorrect!")
            if address_id:
                print(address_id)
            if address_text:
                print(address_text)
            self.last_error_message = "The Address Is Incorrect!"
            return False

    def get_exit(self):
        if getattr(self, "driver", None):
            try:
                self.driver.quit()
            except Exception:
                pass

    def update_all_integrations(self):
        """Update all calendars and send all notifications"""
        if not all([self.year, self.month, self.day]):
            print("No valid bin collection date found. Skipping integrations.")
            return
        if self.integration_manager is None:
            self.integration_manager = IntegrationManager(config=self.config)

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


def main() -> int:
    parser = argparse.ArgumentParser(description="Belfast Black Bin collection checker")
    parser.add_argument("--configure", action="store_true", help="Run interactive setup")
    args = parser.parse_args()

    load_dotenv()
    config_path = os.getenv("CONFIG_PATH", DEFAULT_CONFIG_PATH)
    config = _load_config(config_path)

    bins = BlackBin(config=config, enable_integrations=not args.configure)

    try:
        if args.configure:
            bins.start_chrome()
            config = bins.configure(config_path)
            if not config:
                return 1
            if _prompt_bool("Run a collection check now", default=False):
                bins.config = config
                address = _resolve_address(config)
                if bins.get_bin(address):
                    bins.update_all_integrations()
                else:
                    return 1
            return 0

        address = _resolve_address(config)
        if not address:
            print("No address configuration found. Run with --configure to set it up.")
            return 1

        bins.start_chrome()
        if bins.get_bin(address):
            bins.update_all_integrations()
            return 0
        return 1
    finally:
        bins.get_exit()


if __name__ == '__main__':
    raise SystemExit(main())
