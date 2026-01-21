"""
Microsoft Outlook/Graph API calendar integration
"""
import os
import json
import requests
import time
from datetime import datetime, timedelta
from .calendar_base import CalendarBase


class OutlookCalendar(CalendarBase):
    """Microsoft Outlook/Graph API calendar integration"""

    def __init__(self, token_file: str = 'o365_token.txt'):
        """
        Initialize Outlook Calendar integration

        Args:
            token_file: Path to OAuth 2.0 token file
        """
        self.token_file = token_file
        self.token_data = None
        self.access_token = self._load_and_refresh_token()

    def _load_and_refresh_token(self) -> str:
        """Load token and refresh if expired"""
        try:
            with open(self.token_file, 'r') as f:
                self.token_data = json.load(f)

            # Check if token is expired
            expires_at = self.token_data.get('expires_at', 0)
            current_time = time.time()

            # Refresh if expired or expiring in next 5 minutes
            if current_time >= (expires_at - 300):
                print(f"[Outlook] Token expired or expiring soon, refreshing...")
                if self._refresh_token():
                    print(f"[Outlook] ✓ Token refreshed successfully")
                else:
                    print(f"[Outlook] ✗ Failed to refresh token")
                    return None

            return self.token_data.get('access_token')
        except Exception as e:
            print(f"[Outlook] Error loading token: {e}")
            return None

    def _refresh_token(self) -> bool:
        """Refresh access token using refresh_token"""
        try:
            refresh_token = self.token_data.get('refresh_token')
            if not refresh_token:
                print(f"[Outlook] No refresh_token available")
                return False

            # Get CLIENT_ID from environment
            client_id = os.getenv('CLIENT_ID')
            if not client_id:
                print(f"[Outlook] CLIENT_ID not found in environment")
                return False

            # Microsoft token endpoint
            token_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'

            data = {
                'client_id': client_id,
                'scope': 'https://graph.microsoft.com/Calendars.ReadWrite https://graph.microsoft.com/User.Read offline_access',
                'refresh_token': refresh_token,
                'grant_type': 'refresh_token'
            }

            response = requests.post(token_url, data=data)

            if response.status_code == 200:
                new_token = response.json()

                # Update token data
                self.token_data['access_token'] = new_token['access_token']
                self.token_data['refresh_token'] = new_token.get('refresh_token', refresh_token)
                self.token_data['expires_in'] = new_token.get('expires_in', 3600)
                self.token_data['expires_at'] = time.time() + new_token.get('expires_in', 3600)

                # Save to file
                with open(self.token_file, 'w') as f:
                    json.dump(self.token_data, f, indent=2)

                return True
            else:
                print(f"[Outlook] Token refresh failed: {response.status_code}")
                print(f"[Outlook] Response: {response.text}")
                return False

        except Exception as e:
            print(f"[Outlook] Error refreshing token: {e}")
            return False

    def event_exists(self, title: str, start: datetime, end: datetime) -> bool:
        """Check if event exists on given date"""
        if not self.access_token:
            return False

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        start_str = start.strftime('%Y-%m-%dT%H:%M:%S')
        end_str = end.strftime('%Y-%m-%dT%H:%M:%S')

        events_url = f"https://graph.microsoft.com/v1.0/me/events?$filter=start/dateTime ge '{start_str}' and end/dateTime le '{end_str}'"

        try:
            response = requests.get(events_url, headers=headers)
            if response.status_code == 200:
                events = response.json().get('value', [])
                for event in events:
                    if event.get('subject') == title:
                        print(f"[Outlook] Event '{title}' already exists")
                        return True
            return False
        except Exception as e:
            print(f"[Outlook] Error checking events: {e}")
            return False

    def create_event(self, title: str, start: datetime, end: datetime,
                     location: str = None, reminder_minutes: int = 360) -> bool:
        """Create calendar event in Outlook"""
        if not self.access_token:
            print("[Outlook] Access token not available")
            return False

        # Check if exists first
        if self.event_exists(title, start, end):
            return False

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }

        start_str = start.strftime('%Y-%m-%dT%H:%M:%S')
        end_str = end.strftime('%Y-%m-%dT%H:%M:%S')

        event_data = {
            "subject": title,
            "location": {"displayName": location or ""},
            "start": {
                "dateTime": start_str,
                "timeZone": "UTC"
            },
            "end": {
                "dateTime": end_str,
                "timeZone": "UTC"
            },
            "isAllDay": True,
            "reminderMinutesBeforeStart": reminder_minutes
        }

        create_url = "https://graph.microsoft.com/v1.0/me/events"

        try:
            response = requests.post(create_url, headers=headers, json=event_data)

            if response.status_code == 201:
                print(f"[Outlook] ✓ Event '{title}' created for {start.strftime('%Y-%m-%d')}")
                return True
            else:
                print(f"[Outlook] ✗ Error creating event: {response.status_code}")
                print(f"[Outlook] Response: {response.text}")
                return False
        except Exception as e:
            print(f"[Outlook] Error creating event: {e}")
            return False
