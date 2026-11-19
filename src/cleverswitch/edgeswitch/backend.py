from abc import ABC, abstractmethod


class EdgeBackend(ABC):
    @abstractmethod
    def start(self) -> None: ...

    # Never raises, idempotent, and final: a stopped backend never starts again.
    @abstractmethod
    def stop(self) -> None: ...

    # Starts again if the input source was lost or never came up; a no-op while running or once stopped.
    @abstractmethod
    def revive(self) -> None: ...
