# BlackBin - Belfast Bin Collection Tracker

Automates checking the next Black Bin collection day for a Belfast address (via Belfast City Council site), adds it to your calendar (Outlook/Google), and can publish updates to Home Assistant (MQTT/webhook/REST).

## Requirements

- Docker
- Optional: Python 3.11+ (for non-Docker runs)

## Status

| Integration | Status |
|-------------|--------|
| Selenium scraping | OK |
| Outlook Calendar | OK (automatic token refresh) |
| MQTT | OK (Home Assistant auto-discovery) |
| Google Calendar | OK (service account) |
| HA Webhook | Available (disabled by default) |
| REST API | Available (disabled by default) |

## Quick Start (Docker)

```bash
# 1. Copy environment template
cp .env.example .env

# 2. Start containers (choose one)
./docker_start.sh          # host network
./doc_start.sh             # bridge network

# 3. Open Web UI
http://<your-ip>:5050
```

Config is stored in `/data/blackbin_config.json` and survives container rebuilds.

---

## Configuration

### Option 1: Web UI (recommended)

Open `http://<your-ip>:5050` in a browser. All settings are available:

- **Address** — postcode lookup, address selection, validation
- **Schedule** — visual day/time picker for cron jobs
- **MQTT** — broker, port, credentials, topic
- **Outlook Calendar** — client ID, token generation, calendar selection
- **Google Calendar** — upload service account JSON, calendar selection

Changes are saved to `/data/blackbin_config.json` and applied immediately.

### Option 2: Console (--configure)

Interactive prompts for headless setup:

```bash
docker exec -it blackbin python blackbin.py --configure
```

Configures: address, schedule, MQTT. Calendar settings require Web UI or `.env`.

### Option 3: Environment Variables (.env)

For automation (Docker Compose, Kubernetes). See `.env.example` for full list.

Key variables:

```dotenv
# Outlook
CLIENT_ID=your_client_id
CLIENT_SECRET=your_client_secret
TENANT_ID=common
ENABLE_OUTLOOK=true

# Google Calendar
ENABLE_GOOGLE_CALENDAR=false
GOOGLE_SERVICE_ACCOUNT_FILE=google_service_account.json
GOOGLE_CALENDAR_ID=primary

# MQTT
ENABLE_MQTT=false
MQTT_BROKER=192.168.1.10
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=

# Selenium
SELENIUM_HOST=localhost
SELENIUM_PORT=4444
```

**Precedence:** config file values override `.env`.

---

## Feature Flags

Enable/disable modules via `.env` or Web UI:

| Flag | Default | Description |
|------|---------|-------------|
| `ENABLE_WEB_UI` | `true` | Web interface on port 5050 |
| `ENABLE_OUTLOOK` | `true` | Outlook Calendar integration |
| `ENABLE_GOOGLE_CALENDAR` | `false` | Google Calendar integration |
| `ENABLE_MQTT` | `false` | MQTT publisher (Home Assistant) |
| `ENABLE_HA_WEBHOOK` | `false` | Home Assistant webhook notifier |
| `ENABLE_REST_API` | `false` | REST API endpoint |

Example — run with only MQTT, no calendars:

```bash
docker run -d --name blackbin \
  -e ENABLE_OUTLOOK=false \
  -e ENABLE_MQTT=true \
  -e MQTT_BROKER=192.168.1.10 \
  -v ./data:/data \
  blackbin
```

---

## Integrations

### Outlook Calendar

**Azure Portal setup:**

1. Create an app registration in [Azure Portal](https://portal.azure.com)
2. Set supported account types (use `common` for personal accounts)
3. Add delegated API permissions: `Calendars.ReadWrite`, `User.Read`, `offline_access`
4. Enable "Allow public client flows" (for device code auth)

**Token generation (Web UI):**

1. Enter Client ID and Tenant ID in Outlook section
2. Click "Generate token" under "Token setup / refresh"
3. Open the verification URL, enter the code
4. Click "Complete sign-in" — token saved to `/data/o365_token.txt`

**Token generation (console):**

```bash
docker exec -it blackbin python auth_msal.py
```

**Calendar selection:**

- Click "Fetch calendars" to load your calendars
- Select from dropdown — ID fills automatically
- Or leave empty for default calendar

**Token lifespan:**

- Access tokens expire in ~1 hour (auto-refreshed)
- Refresh tokens last ~90 days (sliding window)
- Re-run token flow only if refresh fails

---

### Google Calendar

**Google Cloud setup:**

1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable Google Calendar API
3. Create a Service Account (IAM → Service Accounts)
4. Download JSON key, save as `google_service_account.json`

**Share calendar with Service Account:**

1. Find service account email in JSON file (field `client_email`):
   ```
   blackbin-calendar@my-project-123456.iam.gserviceaccount.com
   ```
2. Open [Google Calendar](https://calendar.google.com)
3. Settings → select your calendar
4. "Share with specific people or groups" → Add people
5. Paste service account email
6. Permission: **"Make changes to events"**
7. Click Send

**Calendar selection (Web UI):**

1. Upload service account JSON
2. Click "Fetch calendars"
3. Select calendar from dropdown

**Important — calendars don't appear automatically:**

Shared calendars don't auto-appear in Service Account's list. If "Fetch calendars" returns empty:

```bash
docker exec blackbin python -c "
from integrations.google_calendar import GoogleCalendar
gc = GoogleCalendar('/data/google_service_account.json')
calendar_id = 'YOUR_CALENDAR_ID@group.calendar.google.com'
gc.service.calendarList().insert(body={'id': calendar_id}).execute()
print('Calendar added!')
"
```

Get Calendar ID: Google Calendar → Settings → Integrate calendar.
- Custom calendars: `abc123...@group.calendar.google.com`
- Primary calendar: `primary` or owner's email

**Reminders/Notifications:**

Google reminders are per-user. Service Account reminders won't notify you.

Configure default notifications in your calendar:
1. Google Calendar → Settings → your calendar
2. "Event notifications" section
3. Add notification (e.g., 6 hours before)

---

### MQTT (Home Assistant)

Publishes to Home Assistant via MQTT auto-discovery.

**Topics:**

- `homeassistant/sensor/blackbin/config` — discovery config
- `homeassistant/sensor/blackbin/state` — date (`YYYY-MM-DD`)
- `homeassistant/sensor/blackbin/attributes` — JSON metadata

**Setup:**

1. Enable MQTT in Web UI or `.env`
2. Set broker address, port, credentials
3. Entity `sensor.black_bin_collection` appears in Home Assistant

**Custom date format:**

Set `MQTT_STATE_FORMAT` (strftime), e.g., `%a %d %b` → "Wed 29 Jan"

**Home Assistant template (friendly date):**

```yaml
template:
  - sensor:
      - name: "Black Bin Collection Friendly"
        state: >
          {% set raw = states('sensor.black_bin_collection') %}
          {% if raw in ['unknown','unavailable','none',''] %}
            unknown
          {% else %}
            {% set dt = as_datetime(raw) %}
            {% set dow = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][dt.weekday()] %}
            {% set mon = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][dt.month-1] %}
            {{ dow }} {{ '%02d'|format(dt.day) }} {{ mon }}
          {% endif %}
```

---

## Docker Setup

### Host network

```bash
docker run -d --name selenium-server --network host selenium/standalone-chrome
mkdir -p data
docker build -t blackbin .
docker run -d --name blackbin --network host -v ./data:/data blackbin
```

### Bridge network

```bash
docker network create selenium-network
docker run -d --name selenium-server --network selenium-network \
  -p 4444:4444 -p 7900:7900 --shm-size="2g" selenium/standalone-chrome
mkdir -p data
docker build -t blackbin .
docker run -d --name blackbin --network selenium-network \
  -e SELENIUM_HOST=selenium-server -p 5050:5050 -v ./data:/data blackbin
```

### Stop and remove

```bash
docker stop blackbin selenium-server
docker rm blackbin selenium-server
```

---

## Run without Docker

```bash
# Install dependencies
pip install -r requirements.txt

# Start Selenium
docker run -d --name selenium-server -p 4444:4444 selenium/standalone-chrome

# Configure
export CONFIG_PATH=./blackbin_config.json
python blackbin.py --configure

# Run
python blackbin.py

# Web UI (optional)
python web_ui.py
```

---

## Schedule

Default cron: Monday, Friday, Saturday at 19:30; Wednesday at 03:30.

View current schedule:

```bash
docker exec blackbin crontab -l
```

Override via environment:

```bash
CRON_SCHEDULES="30 19 * * 1,5,6;30 3 * * 3"
```

Schedules set in Web UI apply immediately. Manual edits require container restart.

---

## Project Structure

```
blackbin/
├── blackbin.py              # Main script
├── web_ui.py                # Flask Web UI
├── integrations/
│   ├── outlook_calendar.py  # Outlook integration
│   ├── google_calendar.py   # Google Calendar integration
│   └── notifiers/           # MQTT, webhook, REST
├── templates/               # Web UI templates
├── data/                    # Config and tokens (mounted volume)
├── Dockerfile
├── docker_start.sh          # Host network launcher
├── doc_start.sh             # Bridge network launcher
├── .env.example             # Environment template
└── requirements.txt
```

---

## Secrets (do not commit)

- `.env` — credentials and flags
- `o365_token.txt` — Outlook OAuth token
- `google_service_account.json` — Google credentials
- `data/blackbin_config.json` — runtime config
