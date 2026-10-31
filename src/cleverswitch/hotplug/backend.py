from abc import ABC, abstractmethod


class HotplugBackend(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...
