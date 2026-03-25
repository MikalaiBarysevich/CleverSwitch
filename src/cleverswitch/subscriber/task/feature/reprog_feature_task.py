from ..constants import FEATURE_REPROG_CONTROLS_V4_SW_ID
from ..find_divertable_cids_task import FindDivertableCidsTask
from ....hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from ....model.logi_device import LogiDevice
from ....topic.topic import Topic
from .resolve_feature_task import FeatureTask


class ReprogFeatureTask(FeatureTask):

    def __init__(self, device: LogiDevice, topics: dict[str, Topic]) -> None:
        super().__init__("resolve_reprog", device, topics, FEATURE_REPROG_CONTROLS_V4, FEATURE_REPROG_CONTROLS_V4_SW_ID)

    def _fire_dependent_steps(self):
        FindDivertableCidsTask(self._device, self._topics).start()