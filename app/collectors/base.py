from abc import ABC, abstractmethod
from app.models import RawItem


class BaseCollector(ABC):
    @property
    @abstractmethod
    def source_name(self) -> str: ...

    @abstractmethod
    async def collect(self) -> list[RawItem]: ...
