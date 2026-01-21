"""
Home Assistant webhook notifier
"""
import requests
from datetime import datetime
from .notifier_base import NotifierBase


class WebhookNotifier(NotifierBase):
    """Home Assistant webhook notifier"""

    def __init__(self, webhook_url: str):
        """
        Initialize webhook notifier

        Args:
            webhook_url: Full webhook URL (e.g., http://homeassistant.local:8123/api/webhook/blackbin_collection)
        """
        self.webhook_url = webhook_url

    def notify(self, title: str, date: datetime, **kwargs) -> bool:
        """Send webhook notification to Home Assistant"""
        if not self.webhook_url:
            print("[Webhook] URL not configured")
            return False

        try:
            payload = {
                "event": "bin_collection",
                "title": title,
                "date": date.strftime('%Y-%m-%d'),
                "day_of_week": date.strftime('%A'),
                "days_until": (date - datetime.now()).days,
                "timestamp": datetime.now().isoformat()
            }

            response = requests.post(
                self.webhook_url,
                json=payload,
                timeout=10
            )

            if response.status_code in [200, 201]:
                print(f"[Webhook] ✓ Notification sent to Home Assistant")
                return True
            else:
                print(f"[Webhook] ✗ Error: {response.status_code} - {response.text}")
                return False

        except requests.exceptions.ConnectionError as e:
            print(f"[Webhook] ✗ Connection failed: {e}")
            return False
        except Exception as e:
            print(f"[Webhook] ✗ Failed to send notification: {e}")
            return False
