#!/usr/bin/env python3
"""
Google Service Account Setup Helper
Run this to verify your Google Calendar integration setup
"""

import os
import json
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build


def test_google_calendar():
    """Test Google Calendar service account access"""
    load_dotenv()

    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "google_service_account.json")
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

    print("=== Google Calendar Service Account Test ===\n")

    # Check file exists
    if not os.path.exists(service_account_file):
        print(f"❌ Error: Service account file not found: {service_account_file}")
        print("\nSetup instructions:")
        print("1. Go to https://console.cloud.google.com/")
        print("2. Create/select project → Enable Google Calendar API")
        print("3. IAM & Admin → Service Accounts → Create Service Account")
        print("4. Generate JSON key → Save as google_service_account.json")
        return False

    # Load service account info
    with open(service_account_file, 'r') as f:
        sa_info = json.load(f)

    print(f"✓ Service account file found")
    print(f"  Email: {sa_info.get('client_email')}")
    print(f"  Project: {sa_info.get('project_id')}\n")

    # Test authentication
    try:
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file,
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        service = build('calendar', 'v3', credentials=credentials)
        print("✓ Authentication successful\n")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return False

    # Test calendar access
    try:
        calendar = service.calendars().get(calendarId=calendar_id).execute()
        print(f"✓ Calendar access successful")
        print(f"  Calendar: {calendar.get('summary')}")
        print(f"  ID: {calendar.get('id')}\n")
    except Exception as e:
        print(f"❌ Calendar access failed: {e}")
        print("\nMake sure you:")
        print(f"1. Share the calendar with: {sa_info.get('client_email')}")
        print("2. Grant 'Make changes to events' permission")
        return False

    # List recent events
    try:
        events = service.events().list(
            calendarId=calendar_id,
            maxResults=5,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        event_list = events.get('items', [])
        print(f"✓ Calendar has {len(event_list)} upcoming events")

        if event_list:
            print("  Recent events:")
            for event in event_list[:3]:
                print(f"    - {event.get('summary')} ({event.get('start', {}).get('date', 'No date')})")
        print()
    except Exception as e:
        print(f"⚠ Warning: Could not list events: {e}\n")

    print("=== Setup Complete ===")
    print("✓ Google Calendar integration is ready to use")
    return True


if __name__ == '__main__':
    test_google_calendar()
