"""
Abstract base class for calendar integrations
"""
from abc import ABC, abstractmethod
from datetime import datetime


class CalendarBase(ABC):
    """Abstract base class for calendar integrations"""

    @abstractmethod
    def create_event(self, title: str, start: datetime, end: datetime,
                     location: str = None, reminder_minutes: int = 360) -> bool:
        """
        Create calendar event

        Args:
            title: Event title/subject
            start: Event start datetime
            end: Event end datetime
            location: Event location (optional)
            reminder_minutes: Minutes before event to send reminder (default: 360 = 6 hours)

        Returns:
            True if event was created, False if already exists or error occurred
        """
        pass

    @abstractmethod
    def event_exists(self, title: str, start: datetime, end: datetime) -> bool:
        """
        Check if event already exists

        Args:
            title: Event title to search for
            start: Event start datetime
            end: Event end datetime

        Returns:
            True if event exists, False otherwise
        """
        pass
