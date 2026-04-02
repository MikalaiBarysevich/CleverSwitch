from ....hidpp.constants import FEATURE_DEVICE_TYPE_AND_NAME
from ....model.logi_device import LogiDevice
from ....subscriber.task.feature.resolve_feature_task import FeatureTask
from ....topic.topic import Topic
from ..constants import FEATURE_DEVICE_TYPE_AND_NAME_SW_ID
from ..get_device_name_task import GetDeviceNameTask
from ..get_device_type_task import GetDeviceTypeTask


class NameAndTypeFeatureTask(FeatureTask):
    def __init__(self, device: LogiDevice, topics: dict[str, Topic]) -> None:
        super().__init__(
            "resolve_x0005", device, topics, FEATURE_DEVICE_TYPE_AND_NAME, FEATURE_DEVICE_TYPE_AND_NAME_SW_ID
        )

    def _fire_dependent_steps(self):
        GetDeviceTypeTask(self._device, self._topics).start()
        GetDeviceNameTask(self._device, self._topics).start()
