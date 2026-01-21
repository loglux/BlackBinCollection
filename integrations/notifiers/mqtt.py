"""
MQTT publisher for Home Assistant
"""
import json
from datetime import datetime
import paho.mqtt.client as mqtt
from .notifier_base import NotifierBase


class MQTTNotifier(NotifierBase):
    """MQTT publisher for Home Assistant"""

    def __init__(self, broker: str, port: int = 1883, username: str = None,
                 password: str = None, topic: str = "homeassistant/sensor/blackbin"):
        """
        Initialize MQTT notifier

        Args:
            broker: MQTT broker hostname/IP
            port: MQTT broker port (default: 1883)
            username: MQTT username (optional)
            password: MQTT password (optional)
            topic: Base MQTT topic (default: homeassistant/sensor/blackbin)
        """
        self.broker = broker
        self.port = port
        self.username = username
        self.password = password
        self.topic = topic
        self.client = None

    def _connect(self):
        """Connect to MQTT broker"""
        try:
            self.client = mqtt.Client()

            if self.username and self.password:
                self.client.username_pw_set(self.username, self.password)

            self.client.connect(self.broker, self.port, 60)
            return True
        except Exception as e:
            print(f"[MQTT] Connection failed: {e}")
            return False

    def notify(self, title: str, date: datetime, **kwargs) -> bool:
        """Publish bin collection date to MQTT topic"""
        if not self.broker:
            print("[MQTT] Broker not configured")
            return False

        if not self._connect():
            return False

        try:
            # Home Assistant auto-discovery payload
            config_payload = {
                "name": "Black Bin Collection",
                "state_topic": f"{self.topic}/state",
                "json_attributes_topic": f"{self.topic}/attributes",
                "unique_id": "blackbin_belfast",
                "device": {
                    "identifiers": ["blackbin"],
                    "name": "Belfast Bin Collection",
                    "manufacturer": "Custom",
                    "model": "BlackBin v2"
                }
            }

            # State payload (next collection date)
            state_payload = date.strftime('%Y-%m-%d')

            # Attributes payload
            attributes_payload = {
                "title": title,
                "date": date.strftime('%Y-%m-%d'),
                "day_of_week": date.strftime('%A'),
                "days_until": (date - datetime.now()).days,
                "last_update": datetime.now().isoformat()
            }

            # Publish to MQTT
            self.client.publish(f"{self.topic}/config", json.dumps(config_payload), retain=True)
            self.client.publish(f"{self.topic}/state", state_payload, retain=True)
            self.client.publish(f"{self.topic}/attributes", json.dumps(attributes_payload), retain=True)

            self.client.disconnect()

            print(f"[MQTT] ✓ Published to {self.topic}")
            return True

        except Exception as e:
            print(f"[MQTT] ✗ Publish failed: {e}")
            if self.client:
                self.client.disconnect()
            return False
