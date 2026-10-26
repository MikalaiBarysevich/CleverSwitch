from ....hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from ....model.logi_device import LogiDevice
from ....topic.topics import Topics
from ..constants import FEATURE_REPROG_CONTROLS_V4_SW_ID, Task
from ..find_es_cids_flags_task import FindESCidsFlagsTask
from .resolve_feature_task import FeatureTask


class CidReportingFeatureTask(FeatureTask):
    def __init__(self, device: LogiDevice, topics: Topics) -> None:
        super().__init__(
            Task.Feature.Name.CID_REPORTING,
            device,
            topics,
            FEATURE_REPROG_CONTROLS_V4,
            FEATURE_REPROG_CONTROLS_V4_SW_ID,
        )

    # A peer app's getFeature reply on a shared sw_id can look like "not supported". Accepting it would
    # cache a keyboard that is never armed, so keep the step pending and let the orchestrator's cap decide.
    def _unsupported_is_suspect(self) -> bool:
        return self._device.role == "keyboard"

    def _fire_dependent_steps(self):
        FindESCidsFlagsTask(self._device, self._topics).start()
