"""
Abstract base class for notification integrations
"""
from abc import ABC, abstractmethod
from datetime import datetime


class NotifierBase(ABC):
    """Abstract base class for notification integrations"""

    @abstractmethod
    def notify(self, title: str, date: datetime, **kwargs) -> bool:
        """
        Send notification about bin collection

        Args:
            title: Notification title/subject
            date: Bin collection date
            **kwargs: Additional data to include in notification

        Returns:
            True if notification was sent successfully, False otherwise
        """
        pass
