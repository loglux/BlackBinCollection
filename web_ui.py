import argparse
import copy
import json
import os
import secrets
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, flash, get_flashed_messages, render_template, request, url_for
from werkzeug.utils import secure_filename

from blackbin import (
    BlackBin,
    DEFAULT_CONFIG_PATH,
    DEFAULT_SCHEDULES,
    _load_config,
    _parse_human_schedule,
    _resolve_address,
    _save_config,
)
from integrations.outlook_calendar import OutlookCalendar

try:
    from msal import PublicClientApplication
    _MSAL_AVAILABLE = True
except ImportError:
    PublicClientApplication = None
    _MSAL_AVAILABLE = False


_ENV_PATH = Path(__file__).with_name(".env")
if _ENV_PATH.exists():
    load_dotenv(dotenv_path=_ENV_PATH, override=False)
else:
    load_dotenv()

app = Flask(__name__)
secret_key = os.getenv("WEB_UI_SECRET_KEY")
if not secret_key:
    secret_key = secrets.token_hex(16)
app.secret_key = secret_key


@app.route("/favicon.ico")
def _favicon():
    return "", 204


@app.after_request
def _disable_cache(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

_DAY_ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
_DAY_NAME_BY_NUM = {
    0: "sun",
    1: "mon",
    2: "tue",
    3: "wed",
    4: "thu",
    5: "fri",
    6: "sat",
}
_OUTLOOK_SCOPES = ["Calendars.ReadWrite", "User.Read"]
_OUTLOOK_FLOW = None


def _config_path() -> str:
    return os.getenv("CONFIG_PATH", DEFAULT_CONFIG_PATH)


def _load() -> dict:
    return _load_config(_config_path())


def _save(config: dict) -> None:
    _save_config(_config_path(), config)


def _data_dir() -> Path:
    return Path(_config_path()).parent


def _resolve_outlook_token(outlook_config: dict) -> Path | None:
    token_file = outlook_config.get("token_file") or os.getenv("OUTLOOK_TOKEN_FILE") or ""
    if token_file:
        token_path = Path(token_file)
        if token_path.exists():
            return token_path
    default_path = _data_dir() / "o365_token.txt"
    if default_path.exists():
        return default_path
    return None


def _outlook_app(outlook_config: dict) -> tuple[object, str, str]:
    if not _MSAL_AVAILABLE:
        raise RuntimeError("msal is not installed in this environment.")

    client_id = outlook_config.get("client_id") or os.getenv("CLIENT_ID")
    if not client_id:
        raise ValueError("Outlook Client ID is required.")

    tenant_id = outlook_config.get("tenant_id") or os.getenv("TENANT_ID") or "common"
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = PublicClientApplication(client_id, authority=authority)
    return app, client_id, tenant_id


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() == "true"


def _merge_env_defaults(config: dict) -> dict:
    merged = copy.deepcopy(config)

    address = merged.setdefault("address", {})
    if not address.get("postcode"):
        address["postcode"] = os.getenv("POSTCODE", "")
    if not address.get("address_id"):
        address["address_id"] = os.getenv("ADDRESS_ID", "")
    if not address.get("address_text"):
        address["address_text"] = os.getenv("ADDRESS_TEXT", "")

    mqtt = merged.setdefault("mqtt", {})
    if mqtt.get("enabled") is None:
        mqtt["enabled"] = _env_bool("ENABLE_MQTT", False)
    if not mqtt.get("broker"):
        mqtt["broker"] = os.getenv("MQTT_BROKER", "")
    if not mqtt.get("port"):
        try:
            mqtt["port"] = int(os.getenv("MQTT_PORT", "1883"))
        except ValueError:
            mqtt["port"] = 1883
    if not mqtt.get("username"):
        mqtt["username"] = os.getenv("MQTT_USERNAME", "")
    if not mqtt.get("topic"):
        mqtt["topic"] = os.getenv("MQTT_TOPIC", "homeassistant/sensor/blackbin")
    if mqtt.get("state_format") is None:
        mqtt["state_format"] = os.getenv("MQTT_STATE_FORMAT", "")

    calendars = merged.setdefault("calendars", {})
    outlook = calendars.setdefault("outlook", {})
    if outlook.get("enabled") is None:
        outlook["enabled"] = _env_bool("ENABLE_OUTLOOK", True)
    if not outlook.get("client_id"):
        outlook["client_id"] = os.getenv("CLIENT_ID", "")
    if not outlook.get("tenant_id"):
        outlook["tenant_id"] = os.getenv("TENANT_ID", "common")
    if not outlook.get("calendar_name"):
        outlook["calendar_name"] = (
            os.getenv("OUTLOOK_CALENDAR_NAME")
            or os.getenv("CALENDAR_NAME")
            or ""
        )
    if not outlook.get("calendar_id"):
        outlook["calendar_id"] = os.getenv("OUTLOOK_CALENDAR_ID", "")
    if not outlook.get("token_file"):
        env_token = os.getenv("OUTLOOK_TOKEN_FILE")
        if env_token:
            outlook["token_file"] = env_token

    google = calendars.setdefault("google", {})
    if google.get("enabled") is None:
        google["enabled"] = _env_bool("ENABLE_GOOGLE_CALENDAR", False)
    if not google.get("calendar_id"):
        google["calendar_id"] = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    if not google.get("service_account_file"):
        env_service = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        if env_service:
            google["service_account_file"] = env_service

    return merged


def _parse_dow_part(value: str) -> list | None:
    if value == "*":
        return _DAY_ORDER[:]
    days = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start, end = token.split("-", 1)
            if not (start.isdigit() and end.isdigit()):
                return None
            start_i = int(start)
            end_i = int(end)
            if start_i == 7:
                start_i = 0
            if end_i == 7:
                end_i = 0
            if start_i < 0 or start_i > 6 or end_i < 0 or end_i > 6:
                return None
            if start_i <= end_i:
                rng = range(start_i, end_i + 1)
            else:
                rng = list(range(start_i, 7)) + list(range(0, end_i + 1))
            for day in rng:
                name = _DAY_NAME_BY_NUM[day]
                if name not in days:
                    days.append(name)
            continue

        if not token.isdigit():
            return None
        day = int(token)
        if day == 7:
            day = 0
        if day < 0 or day > 6:
            return None
        name = _DAY_NAME_BY_NUM[day]
        if name not in days:
            days.append(name)
    return days


def _cron_to_entry(line: str) -> dict | None:
    parts = line.split()
    if len(parts) < 5:
        return None
    minute, hour, dom, month, dow = parts[:5]
    if dom != "*" or month != "*":
        return None
    if not minute.isdigit() or not hour.isdigit():
        return None
    minute_i = int(minute)
    hour_i = int(hour)
    if minute_i < 0 or minute_i > 59 or hour_i < 0 or hour_i > 23:
        return None
    days = _parse_dow_part(dow)
    if days is None:
        return None
    return {"days": days, "time": f"{hour_i:02d}:{minute_i:02d}"}


def _entry_to_line(entry: dict) -> str:
    time_value = entry.get("time", "").strip()
    days = [day for day in entry.get("days", []) if day]
    if not time_value:
        return ""
    if not days or len(days) == 7:
        return time_value
    return f"{','.join(days)} {time_value}"


def _parse_schedule_entries(lines: list) -> tuple[list, list]:
    entries = []
    custom = []
    for line in lines or []:
        entry = _cron_to_entry(line)
        if entry:
            entries.append(entry)
        else:
            custom.append(line)
    return entries, custom


def _normalize_schedules(text: str, existing: list) -> list:
    if existing is None:
        existing = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return existing or DEFAULT_SCHEDULES[:]

    schedules = []
    for line in lines:
        if len(line.split()) >= 5:
            schedules.append(line)
            continue
        human = _parse_human_schedule(line)
        if human:
            schedules.append(human)
            continue
        raise ValueError(f"Invalid schedule: {line}")
    return schedules


def _build_cron_lines(config: dict) -> list:
    cron = config.get("schedule", {}).get("cron", [])
    if isinstance(cron, str):
        cron = [cron]
    if not cron:
        cron = DEFAULT_SCHEDULES[:]
    return [str(line).strip() for line in cron if str(line).strip()]


def _apply_cron(config: dict) -> tuple[bool, str]:
    lines = _build_cron_lines(config)
    if not lines:
        return False, "No cron schedules found to apply."
    path = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            for line in lines:
                handle.write(
                    f"{line} cd /app && /usr/local/bin/python /app/blackbin.py >/dev/null 2>&1\n"
                )
            path = handle.name
        result = subprocess.run(
            ["crontab", path],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "crontab failed"
            return False, message
    except FileNotFoundError:
        return False, "crontab is not available in this environment."
    except Exception as exc:
        return False, str(exc)
    finally:
        if path:
            try:
                os.unlink(path)
            except Exception:
                pass
    return True, "Cron updated."


def _cron_env_override_hint() -> str | None:
    if os.getenv("CRON_SCHEDULES") or os.getenv("CRON_SCHEDULE"):
        return "CRON_SCHEDULES/CRON_SCHEDULE is set and will override on restart."
    return None


def _lookup_addresses(postcode: str) -> list:
    config = _load()
    bins = BlackBin(config=config, enable_integrations=False)
    bins.start_chrome()
    try:
        select = bins._navigate_to_postcode_search(postcode)
        return bins._extract_addresses(select)
    finally:
        bins.get_exit()


def _run_check(config: dict) -> tuple:
    bins = BlackBin(config=config, enable_integrations=True)
    bins.start_chrome()
    try:
        address = _resolve_address(config)
        if not address:
            return False, "Address configuration is missing."
        if not bins.get_bin(address):
            return False, "No bin collection date available."
        bins.update_all_integrations()
        collected = datetime(bins.year, bins.month, bins.day)
        return True, collected.strftime("%a %Y-%m-%d")
    finally:
        bins.get_exit()


def _validate_address_entry(postcode: str, address_choice: str) -> tuple[bool, str]:
    if "||" not in address_choice:
        return False, "Select a valid address from the list."
    address_id, address_text = address_choice.split("||", 1)
    address = {
        "postcode": postcode,
        "address_id": address_id.strip(),
        "address_text": address_text.strip(),
    }
    bins = BlackBin(config={"address": address}, enable_integrations=False)
    bins.start_chrome()
    try:
        if not bins.get_bin(address):
            message = bins.last_error_message or "Server could not return a bin collection date for this address."
            return False, message
        try:
            collected = datetime(bins.year, bins.month, bins.day)
            return True, f"{address_text.strip()} -> {collected.strftime('%a %Y-%m-%d')}"
        except ValueError:
            return True, f"{address_text.strip()} -> collection date recorded."
    finally:
        bins.get_exit()


def _outlook_token_info(outlook_config: dict) -> dict:
    token_path = _resolve_outlook_token(outlook_config)
    if not token_path:
        return {
            "status": "missing",
            "message": "No token file found. Generate or upload one.",
            "expires_at": None,
        }

    try:
        with open(token_path, "r") as handle:
            token_data = json.load(handle)
    except Exception as exc:
        return {
            "status": "invalid",
            "message": f"Token file unreadable: {exc}",
            "expires_at": None,
        }

    expires_at = token_data.get("expires_at")
    if not isinstance(expires_at, (int, float)):
        return {
            "status": "unknown",
            "message": "Token expiry missing.",
            "expires_at": None,
        }

    now = time.time()
    expires_at = float(expires_at)
    expires_display = datetime.fromtimestamp(expires_at).strftime("%Y-%m-%d %H:%M")
    if expires_at <= now:
        return {
            "status": "expired",
            "message": "Token expired. Generate a new one.",
            "expires_at": expires_display,
        }

    if expires_at - now <= 3 * 24 * 3600:
        return {
            "status": "expiring",
            "message": "Token expiring soon. Consider refreshing.",
            "expires_at": expires_display,
        }

    return {
        "status": "valid",
        "message": "Token is valid.",
        "expires_at": expires_display,
    }


@app.route("/outlook/calendars", methods=["POST"])
def outlook_calendars():
    config = _load()
    outlook_config = config.get("calendars", {}).get("outlook", {})
    token_path = _resolve_outlook_token(outlook_config)
    if not token_path:
        return jsonify({"error": "Outlook token file not found. Upload o365_token.txt first."}), 400

    client_id = outlook_config.get("client_id") or os.getenv("CLIENT_ID")
    if not client_id:
        return jsonify({"error": "Outlook Client ID is required to fetch calendars."}), 400

    tenant_id = outlook_config.get("tenant_id") or os.getenv("TENANT_ID") or "common"
    calendar_client = OutlookCalendar(
        token_file=str(token_path),
        client_id=client_id,
        tenant_id=tenant_id,
    )
    calendars, error = calendar_client.list_calendars()
    if error:
        return jsonify({"error": error}), 400
    if not calendars:
        return jsonify({"error": "No calendars returned."}), 400

    return jsonify({"calendars": calendars})


@app.route("/google/calendars", methods=["POST"])
def google_calendars():
    config = _load()
    google_config = config.get("calendars", {}).get("google", {})

    service_account_file = (
        google_config.get("service_account_file")
        or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    )
    if not service_account_file:
        service_account_file = _data_dir() / "google_service_account.json"

    service_account_path = Path(service_account_file)
    if not service_account_path.exists():
        return jsonify({"error": "Google service account file not found."}), 400

    try:
        from integrations.google_calendar import GoogleCalendar
        calendar_client = GoogleCalendar(str(service_account_path))
        calendars, error = calendar_client.list_calendars()
        if error:
            return jsonify({"error": error}), 400
        if not calendars:
            return jsonify({"error": "No calendars returned."}), 400
        return jsonify({"calendars": calendars})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@app.route("/outlook/token/start", methods=["POST"])
def outlook_token_start():
    outlook_config = _load().get("calendars", {}).get("outlook", {})
    try:
        app, client_id, tenant_id = _outlook_app(outlook_config)
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400

    flow = app.initiate_device_flow(scopes=_OUTLOOK_SCOPES)
    if "user_code" not in flow:
        return jsonify({"error": "Failed to initiate device login."}), 400

    global _OUTLOOK_FLOW
    _OUTLOOK_FLOW = {
        "flow": flow,
        "client_id": client_id,
        "tenant_id": tenant_id,
        "started_at": time.time(),
    }

    return jsonify({
        "user_code": flow.get("user_code"),
        "verification_uri": flow.get("verification_uri"),
        "expires_in": flow.get("expires_in"),
    })


@app.route("/outlook/token/finish", methods=["POST"])
def outlook_token_finish():
    global _OUTLOOK_FLOW
    if not _OUTLOOK_FLOW:
        return jsonify({"error": "Start device login first."}), 400

    flow = _OUTLOOK_FLOW.get("flow", {})
    client_id = _OUTLOOK_FLOW.get("client_id")
    tenant_id = _OUTLOOK_FLOW.get("tenant_id") or "common"
    authority = f"https://login.microsoftonline.com/{tenant_id}"

    try:
        app = PublicClientApplication(client_id, authority=authority)
    except Exception as exc:
        _OUTLOOK_FLOW = None
        return jsonify({"error": f"Failed to create MSAL app: {exc}"}), 400

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        _OUTLOOK_FLOW = None
        message = result.get("error_description") or result.get("error") or "Token request failed."
        return jsonify({"error": message}), 400

    scope = result.get("scope", [])
    if isinstance(scope, str):
        scope = scope.split(" ")

    token_data = {
        "token_type": "Bearer",
        "scope": scope,
        "expires_in": result.get("expires_in", 3600),
        "ext_expires_in": result.get("ext_expires_in", 3600),
        "access_token": result["access_token"],
        "refresh_token": result.get("refresh_token", ""),
        "expires_at": time.time() + result.get("expires_in", 3600),
    }

    token_path = _data_dir() / "o365_token.txt"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as handle:
        import json
        json.dump(token_data, handle, indent=2)

    config = _load()
    outlook = config.setdefault("calendars", {}).setdefault("outlook", {})
    outlook["token_file"] = str(token_path)
    _save(config)

    _OUTLOOK_FLOW = None
    return jsonify({"message": f"Token saved to {token_path}."})


@app.route("/", methods=["GET", "POST"])
def index():
    config = _load()
    messages = get_flashed_messages()
    errors = []
    addresses = []
    form_postcode = ""
    form_address_choice = ""

    if request.method == "POST":
        action = request.form.get("action", "save")
        form_postcode = request.form.get("postcode", "").strip()
        form_address_choice = request.form.get("address_choice", "").strip()

        if action in ("lookup", "validate"):
            postcode = request.form.get("postcode", "").strip()
            if not postcode:
                errors.append("Postcode is required.")
            else:
                try:
                    addresses = _lookup_addresses(postcode)
                    if not addresses:
                        errors.append("No addresses found for that postcode.")
                    elif action == "validate":
                        address_choice = request.form.get("address_choice", "").strip()
                        if not address_choice:
                            errors.append("Select an address after lookup.")
                        else:
                            ok, detail = _validate_address_entry(postcode, address_choice)
                            if ok:
                                messages.append(f"Address validated: {detail}")
                            else:
                                errors.append(detail)
                except Exception as exc:
                    errors.append(f"Address lookup failed: {exc}")

        if action in ("save", "run"):
            # Address
            address_choice = request.form.get("address_choice", "")
            postcode = request.form.get("postcode", "").strip()
            if address_choice and "||" in address_choice:
                address_id, address_text = address_choice.split("||", 1)
                config["address"] = {
                    "postcode": postcode,
                    "address_id": address_id.strip(),
                    "address_text": address_text.strip(),
                }
                messages.append("Address saved.")
            elif postcode and not config.get("address"):
                errors.append("Select an address after lookup.")

            # Schedule
            schedule_entries = [
                entry.strip() for entry in request.form.getlist("schedule_entry") if entry.strip()
            ]
            schedule_text = request.form.get("schedule", "")
            if schedule_entries:
                manual_lines = [line for line in schedule_text.splitlines() if line.strip()]
                schedule_text = "\n".join(schedule_entries + manual_lines)
            try:
                existing = config.get("schedule", {}).get("cron", [])
                schedules = _normalize_schedules(schedule_text, existing)
                config["schedule"] = {"cron": schedules}
                applied, detail = _apply_cron(config)
                if applied:
                    messages.append("Schedule saved and applied.")
                    hint = _cron_env_override_hint()
                    if hint:
                        messages.append(hint)
                else:
                    messages.append("Schedule saved.")
                    errors.append(f"Schedule apply failed: {detail}")
            except ValueError as exc:
                errors.append(str(exc))

            # MQTT
            mqtt_enabled = request.form.get("mqtt_enabled") == "on"
            existing_mqtt = config.get("mqtt", {})
            if mqtt_enabled:
                broker = request.form.get("mqtt_broker", "").strip()
                if not broker:
                    errors.append("MQTT broker is required when MQTT is enabled.")
                else:
                    mqtt_password = request.form.get("mqtt_password", "").strip()
                    if not mqtt_password:
                        mqtt_password = existing_mqtt.get("password")
                    config["mqtt"] = {
                        "enabled": True,
                        "broker": broker,
                        "port": int(request.form.get("mqtt_port", "1883").strip() or "1883"),
                        "username": request.form.get("mqtt_username", "").strip() or None,
                        "password": mqtt_password or None,
                        "topic": request.form.get("mqtt_topic", "").strip() or "homeassistant/sensor/blackbin",
                        "state_format": request.form.get("mqtt_state_format", "").strip() or None,
                    }
                    messages.append("MQTT settings saved.")
            else:
                config["mqtt"] = {**existing_mqtt, "enabled": False}

            # Outlook calendar
            calendars = config.setdefault("calendars", {})
            outlook_enabled = request.form.get("outlook_enabled") == "on"
            outlook = calendars.setdefault("outlook", {})
            outlook["enabled"] = outlook_enabled
            outlook_client_id = request.form.get("outlook_client_id", "").strip()
            outlook_client_secret = request.form.get("outlook_client_secret", "").strip()
            outlook_tenant_id = request.form.get("outlook_tenant_id", "").strip()
            outlook_calendar_name = request.form.get("outlook_calendar_name", "").strip()
            outlook_calendar_id = request.form.get("outlook_calendar_id", "").strip()
            if outlook_client_id:
                outlook["client_id"] = outlook_client_id
            if outlook_client_secret:
                outlook["client_secret"] = outlook_client_secret
            if outlook_tenant_id:
                outlook["tenant_id"] = outlook_tenant_id
            outlook["calendar_name"] = outlook_calendar_name or None
            outlook["calendar_id"] = outlook_calendar_id or None

            outlook_upload = request.files.get("outlook_token_file")
            if outlook_upload and outlook_upload.filename:
                filename = secure_filename(outlook_upload.filename) or "o365_token.txt"
                token_path = _data_dir() / "o365_token.txt"
                token_path.parent.mkdir(parents=True, exist_ok=True)
                outlook_upload.save(token_path)
                outlook["token_file"] = str(token_path)
                messages.append("Outlook token file uploaded.")

            # Google calendar
            google_enabled = request.form.get("google_enabled") == "on"
            google = calendars.setdefault("google", {})
            google["enabled"] = google_enabled
            google_calendar_id = request.form.get("google_calendar_id", "").strip()
            if google_calendar_id:
                google["calendar_id"] = google_calendar_id

            google_upload = request.files.get("google_service_account_file")
            if google_upload and google_upload.filename:
                filename = secure_filename(google_upload.filename) or "google_service_account.json"
                google_path = _data_dir() / "google_service_account.json"
                google_path.parent.mkdir(parents=True, exist_ok=True)
                google_upload.save(google_path)
                google["service_account_file"] = str(google_path)
                messages.append("Google service account file uploaded.")

            _save(config)

            if action == "run" and not errors:
                ok, detail = _run_check(config)
                config["last_run"] = {
                    "status": "ok" if ok else "error",
                    "message": detail,
                    "timestamp": time.time(),
                }
                _save(config)
                if ok:
                    flash("Run completed.")
                    return redirect(url_for("index"))
                errors.append(detail)
            if action == "save" and not errors:
                flash("Settings saved.")
                return redirect(url_for("index"))

    display_config = _merge_env_defaults(config)
    schedule_cron = display_config.get("schedule", {}).get("cron", []) or []
    schedule_entries, schedule_custom = _parse_schedule_entries(schedule_cron)
    if not schedule_entries and not schedule_custom:
        schedule_entries = [
            {"days": ["mon", "fri", "sat"], "time": "19:30"},
            {"days": ["wed"], "time": "03:30"},
        ]
    for entry in schedule_entries:
        entry["line"] = _entry_to_line(entry)

    schedule_lines = "\n".join(schedule_custom)
    address_summary = display_config.get("address", {}).get("address_text")
    outlook_secret_present = bool(
        config.get("calendars", {}).get("outlook", {}).get("client_secret") or os.getenv("CLIENT_SECRET")
    )
    mqtt_password_present = bool(
        config.get("mqtt", {}).get("password") or os.getenv("MQTT_PASSWORD")
    )
    outlook_token_info = _outlook_token_info(config.get("calendars", {}).get("outlook", {}))
    outlook_token_present = outlook_token_info.get("status") != "missing"
    google_token_present = bool(
        config.get("calendars", {}).get("google", {}).get("service_account_file")
        or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        or (_data_dir() / "google_service_account.json").exists()
    )
    saved_address = display_config.get("address", {})
    saved_address_choice = ""
    if saved_address.get("address_id") and saved_address.get("address_text"):
        saved_address_choice = f"{saved_address['address_id']}||{saved_address['address_text']}"
    postcode_value = form_postcode or display_config.get("address", {}).get("postcode", "")
    selected_address_choice = form_address_choice or saved_address_choice
    last_run = display_config.get("last_run", {}) or {}
    last_run_message = last_run.get("message")
    last_run_status = last_run.get("status")
    last_run_time = None
    if last_run.get("timestamp"):
        try:
            last_run_time = datetime.fromtimestamp(last_run["timestamp"]).strftime("%a %Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            last_run_time = None

    return render_template(
        "index.html",
        config=display_config,
        postcode_value=postcode_value,
        selected_address_choice=selected_address_choice,
        schedule_lines=schedule_lines,
        schedule_entries=schedule_entries,
        address_summary=address_summary,
        addresses=addresses,
        messages=messages,
        errors=errors,
        outlook_secret_present=outlook_secret_present,
        mqtt_password_present=mqtt_password_present,
        outlook_token_present=outlook_token_present,
        outlook_token_info=outlook_token_info,
        google_token_present=google_token_present,
        last_run_message=last_run_message,
        last_run_status=last_run_status,
        last_run_time=last_run_time,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="BlackBin Web UI")
    parser.add_argument("--host", default=os.getenv("WEB_UI_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("WEB_UI_PORT", "5050")))
    args = parser.parse_args()

    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
