# BlackBin - Belfast Bin Collection Tracker

BlackBin automates checking the next Black Bin collection day for a Belfast address (via the Belfast City Council site), adds it to your Outlook Calendar, and can publish updates to Home Assistant (MQTT/webhook/REST).

## Requirements

- Docker
- Optional: Python 3.11+ (for non-Docker runs)

## Status

Working:
- Selenium scraping (Belfast City Council)
- Outlook Calendar (automatic token refresh)
- MQTT -> Home Assistant (auto-discovery sensor)

Partial/optional:
- Google Calendar (service account, disabled by default)
- HA Webhook (disabled by default)
- REST API (disabled by default)

## Quick start (Docker)

1) Copy `.env.example` to `.env` and fill in calendar credentials (Outlook/Google).
   If you prefer configuring in the Web UI, you can add Outlook Client ID / Tenant ID there instead.

```bash
cp .env.example .env
```
2) Start containers:
   - `./docker_start.sh` (host network, Selenium at `localhost:4444`)
   - or `./doc_start.sh` (bridge network, Selenium at `selenium-server:4444`)
3) Run interactive setup (address + schedule + MQTT):

```bash
docker exec -it blackbin python blackbin.py --configure
```
4) Check logs:

```bash
docker logs blackbin --tail 50
```

Web UI (enabled by default):

- Host network: `http://<host-ip>:5050`
- Bridge network: `http://<host-ip>:5050` (port mapped in `doc_start.sh`)

Config is stored in `/data/blackbin_config.json` (mounted via `./data:/data` in the start scripts) so it survives rebuilds.
If you keep tokens in `/data` (recommended), you do not need to rebuild after updating them.
If you change `.env` on the host, rebuild the image or copy the file into the running container.

## Manual Docker setup (bridge network)

```bash
docker network create selenium-network
docker run -d --name selenium-server --network selenium-network -p 4444:4444 -p 7900:7900 --shm-size="2g" selenium/standalone-chrome
mkdir -p data
docker build -t blackbin .
docker run -d --name blackbin --network selenium-network -e SELENIUM_HOST=selenium-server -p 5050:5050 -v ./data:/data blackbin
```

## Manual Docker setup (host network)

```bash
docker run -d --name selenium-server --network host selenium/standalone-chrome
mkdir -p data
docker build -t blackbin .
docker run -d --name blackbin --network host -v ./data:/data blackbin
```

## Manual run

```bash
docker exec -it blackbin python blackbin.py --configure
docker exec blackbin python blackbin.py
```

## Run without Docker

1) Install dependencies:

```bash
pip install -r requirements.txt
```

2) Start a Selenium server (example):

```bash
docker run -d --name selenium-server -p 4444:4444 selenium/standalone-chrome
```

3) Run interactive setup:

```bash
export CONFIG_PATH=./blackbin_config.json
python blackbin.py --configure
```

4) Start web UI (optional):

```bash
export WEB_UI_HOST=0.0.0.0
export WEB_UI_PORT=5050
python web_ui.py
```

5) Run:

```bash
python blackbin.py
```

## Stop and remove containers

```bash
docker stop blackbin selenium-server
docker rm blackbin selenium-server
```

## Schedule

Default cron: Monday, Friday, Saturday at 19:30; Wednesday at 03:30 (container timezone).
Schedules saved in the Web UI are applied immediately. If you edit `blackbin_config.json` by hand or
use `--configure`, restart the container to re-apply cron.

```bash
docker exec blackbin crontab -l
```

Override via env (restart required):

```bash
CRON_SCHEDULES="30 19 * * 1,5,6;30 3 * * 3"
```

## Selenium endpoint

`blackbin` connects to `http://<SELENIUM_HOST>:<SELENIUM_PORT>/wd/hub`.
Defaults: `SELENIUM_HOST=localhost`, `SELENIUM_PORT=4444`.

## Web UI

Enabled by default. You can disable it with `ENABLE_WEB_UI=false`.

Config:
- `WEB_UI_HOST` (default `0.0.0.0`)
- `WEB_UI_PORT` (default `5050`)
- `WEB_UI_SECRET_KEY` (set to a fixed secret so Flask can store flash messages, defaults to a random value if unset)

Access from another machine: `http://<host-ip>:5050`
Outlook token setup is available under "Token setup / refresh" in the Outlook section.

## Integrations

### Active

| Integration | Status |
|------------|--------|
| Outlook Calendar | OK (automatic token refresh) |
| MQTT | OK (sensor.black_bin_collection in HA) |
| Selenium scraping | OK |

### Disabled by default (not tested recently)

| Integration | Flag in .env |
|------------|-------------|
| Google Calendar | ENABLE_GOOGLE_CALENDAR=false |
| HA Webhook | ENABLE_HA_WEBHOOK=false |
| REST API | ENABLE_REST_API=false |

## MQTT (Home Assistant)

BlackBin publishes Home Assistant MQTT discovery plus state and attributes. Make sure the MQTT integration
is configured in Home Assistant.

Default base topic: `homeassistant/sensor/blackbin`

Topics:
- `<base>/config` (retained) - MQTT discovery config
- `<base>/state` (retained) - next collection date as `YYYY-MM-DD`
- `<base>/attributes` (retained) - JSON attributes: `title`, `date`, `day_of_week`, `days_until`, `last_update` (and `date_formatted` if enabled)

You can set MQTT values during `--configure` and they will be stored in the local config file.
Manual `.env` settings are still supported.
If you set `MQTT_STATE_FORMAT`, the state payload will use that format and an extra `date_formatted`
attribute will be added.

Example `.env`:

```dotenv
ENABLE_MQTT=true
MQTT_BROKER=192.168.1.10
MQTT_PORT=1883
MQTT_USERNAME=blackbin
MQTT_PASSWORD=secret
MQTT_TOPIC=homeassistant/sensor/blackbin
MQTT_STATE_FORMAT=%a %d %b
```

Home Assistant UI example (friendly date like "Wed 29 Jan"):

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

Entity card:

```yaml
type: entity
entity: sensor.black_bin_collection_friendly
```

Replace `sensor.black_bin_collection` with your entity id if it differs.

## Configuration

Address, schedule, and MQTT are stored in the local config file created by `--configure`.
Default path: `/data/blackbin_config.json` (override with `CONFIG_PATH`).

Config precedence: values in `/data/blackbin_config.json` override `.env`. The UI writes to the config file.
Set secrets in `.env` if you prefer environment-based configuration (do not commit it).
Common settings:

Minimum config (Outlook only):

```dotenv
CLIENT_ID=your_client_id
CLIENT_SECRET=your_client_secret
TENANT_ID=common
ENABLE_OUTLOOK=true
```

When you are tuning the address, the Web UI now exposes a “Validate address” button (next to
“Lookup addresses”). It fetches the Belfast City Hall lookup results (e.g. “2 Donegall Square East,
Belfast, BT1 5HB”) without saving anything; use it to confirm the postcode/address combination
before pressing Save.

- `CLIENT_ID`, `CLIENT_SECRET`
- `TENANT_ID` (use `common` for personal accounts)
- `OUTLOOK_CALENDAR_NAME` (optional)
- `OUTLOOK_CALENDAR_ID` (optional, preferred for exact targeting)
- `OUTLOOK_TOKEN_FILE` (optional path to `o365_token.txt`)
- `ENABLE_OUTLOOK`, `ENABLE_GOOGLE_CALENDAR`
- `ENABLE_MQTT`, `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_TOPIC`, `MQTT_STATE_FORMAT`
- `ENABLE_HA_WEBHOOK`, `HA_WEBHOOK_URL`
- `ENABLE_REST_API`, `REST_API_HOST`, `REST_API_PORT`
- `SELENIUM_HOST`, `SELENIUM_PORT`
- `GOOGLE_SERVICE_ACCOUNT_FILE`, `GOOGLE_CALENDAR_ID`
- `CONFIG_PATH` (optional local config path)

## Outlook Calendar setup

1) Create an app registration in Azure Portal.
2) Set supported account types as needed (use `common` for personal accounts).
3) Add delegated API permissions: `Calendars.ReadWrite`, `User.Read`, `offline_access`.
4) Enable "Allow public client flows" (device code).
5) Set `.env` with `CLIENT_ID`, `CLIENT_SECRET`, `TENANT_ID` (or enter these in the Web UI).
6) Generate a token file (Web UI or console):

Web UI (recommended):
- Open "Token setup / refresh".
- Click "Generate token" to get the URL + code.
- Complete sign-in in the browser.
- Click "Complete sign-in" to save `/data/o365_token.txt`.

Console (manual):

```bash
# Install msal if missing
pip install msal

# Generate token (creates o365_token.txt in the current directory)
python auth_msal.py
```

If you run the console flow inside Docker:

```bash
docker exec -it blackbin python auth_msal.py
```

Copy or upload the resulting `o365_token.txt` into `/data` (or upload via the Web UI).

Token refresh:
- Automatic during normal runs (uses refresh_token).
- If refresh fails or access is revoked, re-run the token flow (Web UI or console).

Calendar selection:
- Use "Fetch calendars" in the Web UI to select a calendar.
- If `OUTLOOK_CALENDAR_NAME` / `OUTLOOK_CALENDAR_ID` are empty, the default calendar is used.

**Token lifespan**

- Access tokens expire after about one hour (security requirement), but BlackBin stores the refresh token in `/data/o365_token.txt` and renews the access token every run.
- The refresh token itself has a ~90-day sliding lifetime; each successful refresh resets the clock. You only need to re-run the token flow if the refresh token hasn’t been used for 90 days or it’s rejected (revoked consent, changed client secrets, tenant policy, etc.).

## Google Calendar setup (service account)

1) Create a Google Cloud project and enable Google Calendar API.
2) Create a Service Account and download a JSON key.
3) Save the key as `google_service_account.json` in the project root (or upload via Web UI).
4) Share the target Google Calendar with the service account email (permission: "Make changes to events").
5) Set `.env`:

```dotenv
ENABLE_GOOGLE_CALENDAR=true
GOOGLE_SERVICE_ACCOUNT_FILE=google_service_account.json
GOOGLE_CALENDAR_ID=primary
```

Calendar selection (Web UI):
- Upload service account JSON in the Google Calendar section.
- Click "Fetch calendars" to load available calendars.
- Select a calendar from the dropdown — Calendar ID fills automatically.

**Important:** Shared calendars don't appear automatically in the Service Account's calendar list.
If "Fetch calendars" returns empty, add the calendar manually:

```bash
docker exec blackbin python -c "
from integrations.google_calendar import GoogleCalendar
gc = GoogleCalendar('/data/google_service_account.json')
calendar_id = 'YOUR_CALENDAR_ID@group.calendar.google.com'
gc.service.calendarList().insert(body={'id': calendar_id}).execute()
print('Calendar added!')
"
```

Get Calendar ID from Google Calendar → Settings → Integrate calendar.

Optional test:

```bash
python auth_google.py
```

## Rebuild after changes

After code changes, rebuild and restart containers (stop/remove and re-run your chosen start script).

## Project structure

```
blackbin/
├── README.md                   # This file
├── blackbin.py                 # Main script
├── integrations/               # Modular integrations
│   ├── outlook_calendar.py     # Outlook (active)
│   ├── google_calendar.py      # Google Calendar
│   └── notifiers/              # Home Assistant notifiers
├── Dockerfile
├── docker_start.sh
├── doc_start.sh
├── data/                       # Local config storage
│   └── blackbin_config.json    # Created by --configure
└── .env                        # Secrets (do not commit)
```

## Important

Secrets to keep out of git:
- `.env` - client IDs, secrets, and flags
- `o365_token.txt` - OAuth token
- `data/blackbin_config.json` - local runtime config
- `google_service_account.json` - Google credentials
