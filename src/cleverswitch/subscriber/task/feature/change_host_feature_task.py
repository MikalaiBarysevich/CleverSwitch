from ....hidpp.constants import FEATURE_CHANGE_HOST
from ....model.logi_device import LogiDevice
from ....topic.topic import Topic
from ..constants import FEATURE_CHANGE_HOST_SW_ID
from .resolve_feature_task import FeatureTask


class ChangeHostFeatureTask(FeatureTask):
    def __init__(self, device: LogiDevice, topics: dict[str, Topic]) -> None:
        super().__init__("resolve_change_host", device, topics, FEATURE_CHANGE_HOST, FEATURE_CHANGE_HOST_SW_ID)
