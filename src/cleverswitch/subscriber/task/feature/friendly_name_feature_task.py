from ....hidpp.constants import FEATURE_DEVICE_FRIENDLY_NAME
from ....model.logi_device import LogiDevice
from ....subscriber.task.feature.resolve_feature_task import FeatureTask
from ....topic.topics import Topics
from ..constants import FEATURE_DEVICE_FRIENDLY_NAME_SW_ID, Task
from ..get_device_friendly_name_task import GetDeviceFriendlyNameTask


class FriendlyNameFeatureTask(FeatureTask):
    def __init__(self, device: LogiDevice, topics: Topics) -> None:
        super().__init__(
            Task.Feature.Name.FRIENDLY_NAME,
            device,
            topics,
            FEATURE_DEVICE_FRIENDLY_NAME,
            FEATURE_DEVICE_FRIENDLY_NAME_SW_ID,
        )

    def _fire_dependent_steps(self):
        GetDeviceFriendlyNameTask(self._device, self._topics).start()
