from abc import ABC, abstractmethod
from typing import Any


class BaseChannel(ABC):
    name: str

    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        pass

    @abstractmethod
    async def receive(self, payload: Any) -> Any:
        pass

    @abstractmethod
    async def send(self, recipient: str | int, message: str) -> None:
        pass
