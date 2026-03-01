"""Base class for platform publishers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class PublishResult:
    platform: str
    success: bool
    message: str = ""
    url: str = ""


class Publisher(ABC):
    """Abstract base for posting content to a platform."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        ...

    @abstractmethod
    def publish(self, content: str, **kwargs) -> PublishResult:
        ...

    @abstractmethod
    def is_configured(self) -> bool:
        ...
