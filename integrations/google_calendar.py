"""
Google Calendar integration using Service Account
"""
import os
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from .calendar_base import CalendarBase


class GoogleCalendar(CalendarBase):
    """Google Calendar integration using Service Account"""

    SCOPES = ['https://www.googleapis.com/auth/calendar']

    def __init__(self, service_account_file: str, calendar_id: str = 'primary'):
        """
        Initialize Google Calendar integration

        Args:
            service_account_file: Path to JSON credentials file
            calendar_id: Calendar ID (or 'primary' for default)
        """
        self.calendar_id = calendar_id
        self.service = self._authenticate(service_account_file)

    def _authenticate(self, service_account_file: str):
        """Authenticate using service account"""
        try:
            if not os.path.exists(service_account_file):
                print(f"[Google Calendar] Service account file not found: {service_account_file}")
                return None

            credentials = service_account.Credentials.from_service_account_file(
                service_account_file, scopes=self.SCOPES)
            return build('calendar', 'v3', credentials=credentials)
        except Exception as e:
            print(f"[Google Calendar] Authentication failed: {e}")
            return None

    def event_exists(self, title: str, start: datetime, end: datetime) -> bool:
        """Check if event exists on given date"""
        if not self.service:
            return False

        try:
            # Query events on that date
            time_min = start.isoformat() + 'Z'
            time_max = end.isoformat() + 'Z'

            events_result = self.service.events().list(
                calendarId=self.calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()

            events = events_result.get('items', [])

            # Check if event with same title exists
            for event in events:
                if event.get('summary') == title:
                    print(f"[Google Calendar] Event '{title}' already exists")
                    return True

            return False
        except HttpError as e:
            print(f"[Google Calendar] Error checking events: {e}")
            return False

    def create_event(self, title: str, start: datetime, end: datetime,
                     location: str = None, reminder_minutes: int = 360) -> bool:
        """Create calendar event in Google Calendar"""
        if not self.service:
            print("[Google Calendar] Service not available")
            return False

        # Check if exists first
        if self.event_exists(title, start, end):
            return False

        try:
            event = {
                'summary': title,
                'location': location or '',
                'start': {
                    'date': start.strftime('%Y-%m-%d'),
                    'timeZone': 'Europe/London',
                },
                'end': {
                    'date': end.strftime('%Y-%m-%d'),
                    'timeZone': 'Europe/London',
                },
                'reminders': {
                    'useDefault': False,
                    'overrides': [
                        {'method': 'popup', 'minutes': reminder_minutes},
                    ],
                },
            }

            created_event = self.service.events().insert(
                calendarId=self.calendar_id, body=event).execute()

            print(f"[Google Calendar] ✓ Event '{title}' created for {start.strftime('%Y-%m-%d')}")
            print(f"[Google Calendar] Event ID: {created_event.get('id')}")
            return True

        except HttpError as e:
            print(f"[Google Calendar] ✗ Error creating event: {e}")
            return False

    def list_calendars(self) -> tuple[list, str | None]:
        """Return available calendars as a list of dicts with id/name."""
        if not self.service:
            return [], "Service not authenticated"

        try:
            calendar_list = self.service.calendarList().list().execute()
            results = []
            for calendar in calendar_list.get('items', []):
                cal_id = calendar.get('id', '')
                name = calendar.get('summary', cal_id)
                if cal_id:
                    results.append({"id": cal_id, "name": name})
            return results, None
        except Exception as e:
            return [], f"Error listing calendars: {e}"
