from abc import ABC, abstractmethod
from app.models import GeneratedContent


class BasePublisher(ABC):
    @property
    @abstractmethod
    def channel_name(self) -> str: ...

    @property
    @abstractmethod
    def is_enabled(self) -> bool: ...

    @abstractmethod
    async def publish(self, content: GeneratedContent) -> dict: ...
