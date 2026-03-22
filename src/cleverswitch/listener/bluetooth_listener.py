from ..event.device_connected_event import DeviceConnectedEvent
from ..listener.event_listener import EventListener


class BluetoothListener(EventListener):

    def run(self):
        # self._topics["event_topic"].publish(DeviceConnectedEvent(
        #     slot=0xFF,
        #     pid=self._device_info.pid,
        #     link_established=True,
        #     wpid=self._device_info.pid,
        # ))
        super().run()
