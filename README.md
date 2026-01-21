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

1) Copy `.env.example` to `.env` and fill in your values.

```bash
cp .env.example .env
```
2) Start containers:
   - `./docker_start.sh` (host network, Selenium at `localhost:4444`)
   - or `./doc_start.sh` (bridge network, Selenium at `selenium-server:4444`)
3) Check logs:

```bash
docker logs blackbin --tail 50
```

Note: The Docker image copies `.env` and `o365_token.txt` at build time. After changing either file, rebuild
the image (stop/remove containers and re-run your chosen start script).

## Manual Docker setup (bridge network)

```bash
docker network create selenium-network
docker run -d --name selenium-server --network selenium-network -p 4444:4444 -p 7900:7900 --shm-size="2g" selenium/standalone-chrome
docker build -t blackbin .
docker run -d --name blackbin --network selenium-network -e SELENIUM_HOST=selenium-server blackbin
```

## Manual Docker setup (host network)

```bash
docker run -d --name selenium-server --network host selenium/standalone-chrome
docker build -t blackbin .
docker run -d --name blackbin --network host blackbin
```

## Manual run

```bash
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

3) Run:

```bash
python blackbin.py
```

## Stop and remove containers

```bash
docker stop blackbin selenium-server
docker rm blackbin selenium-server
```

## Schedule

Cron: Monday, Friday, Saturday at 19:30; Wednesday at 03:30 (container timezone).

```bash
docker exec blackbin crontab -l
```

## Selenium endpoint

`blackbin` connects to `http://<SELENIUM_HOST>:<SELENIUM_PORT>/wd/hub`.
Defaults: `SELENIUM_HOST=localhost`, `SELENIUM_PORT=4444`.

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
- `<base>/attributes` (retained) - JSON attributes: `title`, `date`, `day_of_week`, `days_until`, `last_update`

Example `.env`:

```dotenv
ENABLE_MQTT=true
MQTT_BROKER=192.168.1.10
MQTT_PORT=1883
MQTT_USERNAME=blackbin
MQTT_PASSWORD=secret
MQTT_TOPIC=homeassistant/sensor/blackbin
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

Set values in `.env` and do not commit it. Common settings:

Minimum config (Outlook only):

```dotenv
HOUSE_ADDRESS=3 Anna Street, Belfast, BT1 1AA
CLIENT_ID=your_client_id
CLIENT_SECRET=your_client_secret
TENANT_ID=common
ENABLE_OUTLOOK=true
```

- `HOUSE_ADDRESS` (format: `Street Name, Belfast, POSTCODE`, e.g. `3 Anna Street, Belfast, BT1 1AA`; must match the address list on the Belfast site)
- `CLIENT_ID`, `CLIENT_SECRET`
- `TENANT_ID` (use `common` for personal accounts)
- `ENABLE_OUTLOOK`, `ENABLE_GOOGLE_CALENDAR`
- `ENABLE_MQTT`, `MQTT_BROKER`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_TOPIC`
- `ENABLE_HA_WEBHOOK`, `HA_WEBHOOK_URL`
- `ENABLE_REST_API`, `REST_API_HOST`, `REST_API_PORT`
- `SELENIUM_HOST`, `SELENIUM_PORT`
- `GOOGLE_SERVICE_ACCOUNT_FILE`, `GOOGLE_CALENDAR_ID`

## Outlook Calendar setup

1) Create an app registration in Azure Portal.
2) Set supported account types as needed (use `common` for personal accounts).
3) Add delegated API permissions: `Calendars.ReadWrite`, `User.Read`, `offline_access`.
4) Enable "Allow public client flows" (device code).
5) Set `.env` with `CLIENT_ID`, `CLIENT_SECRET`, `TENANT_ID`.
6) Generate a token file:

```bash
# Install msal if missing
pip install msal

# Generate token (creates o365_token.txt in the current directory)
python auth_msal.py
```

The token auto-refreshes during normal runs and is stored in `o365_token.txt`.
In Docker, `.env` and `o365_token.txt` are baked into the image at build time. If you update them on the host,
rebuild the image (e.g. `./safe_upgrade.sh`) or update them inside the running container.

## Google Calendar setup (service account)

1) Create a Google Cloud project and enable Google Calendar API.
2) Create a Service Account and download a JSON key.
3) Save the key as `google_service_account.json` in the project root.
4) Share the target Google Calendar with the service account email (permission: "Make changes to events").
5) Set `.env`:

```dotenv
ENABLE_GOOGLE_CALENDAR=true
GOOGLE_SERVICE_ACCOUNT_FILE=google_service_account.json
GOOGLE_CALENDAR_ID=primary
```

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
└── .env                        # Configuration (do not commit)
```

## Important

Secrets to keep out of git:
- `.env` - client IDs, secrets, and flags
- `o365_token.txt` - OAuth token
- `google_service_account.json` - Google credentials
