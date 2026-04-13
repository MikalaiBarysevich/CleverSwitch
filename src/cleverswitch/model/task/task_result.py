import dataclasses

from .status import Status


@dataclasses.dataclass
class TaskResult:
    status: Status
