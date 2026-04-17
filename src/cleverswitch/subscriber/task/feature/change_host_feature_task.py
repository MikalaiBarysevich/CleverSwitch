from ....hidpp.constants import FEATURE_CHANGE_HOST
from ....model.logi_device import LogiDevice
from ....topic.topics import Topics
from ..constants import FEATURE_CHANGE_HOST_SW_ID, Task
from .resolve_feature_task import FeatureTask


class ChangeHostFeatureTask(FeatureTask):
    def __init__(self, device: LogiDevice, topics: Topics) -> None:
        super().__init__(Task.Feature.Name.CHANGE_HOST, device, topics, FEATURE_CHANGE_HOST, FEATURE_CHANGE_HOST_SW_ID)
