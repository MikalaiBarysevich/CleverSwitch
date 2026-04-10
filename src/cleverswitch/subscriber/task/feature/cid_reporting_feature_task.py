from ....hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from ....model.logi_device import LogiDevice
from ....topic.topics import Topics
from ..constants import FEATURE_REPROG_CONTROLS_V4_SW_ID
from ..find_es_cids_flags_task import FindESCidsFlagsTask
from .resolve_feature_task import FeatureTask


class CidReportingFeatureTask(FeatureTask):
    def __init__(self, device: LogiDevice, topics: Topics) -> None:
        super().__init__("resolve_reprog", device, topics, FEATURE_REPROG_CONTROLS_V4, FEATURE_REPROG_CONTROLS_V4_SW_ID)

    def _fire_dependent_steps(self):
        FindESCidsFlagsTask(self._device, self._topics).start()
