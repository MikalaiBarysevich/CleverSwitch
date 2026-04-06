import argparse
import logging
import signal
import sys
import threading

from .. import __version__
from ..config import config as cfg_module
from ..config.config import Config
from ..errors.errors import ConfigError
from ..model.context.app_context import AppContext
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.device_connected_subscriber import DeviceConnectionSubscriber
from ..subscriber.device_info_subscriber import DeviceInfoSubscriber
from ..subscriber.disconnect_poller_subscriber import DisconnectPollerSubscriber
from ..subscriber.divert_subscriber import DivertSubscriber
from ..subscriber.diverted_host_change_subscriber import DivertedHostChangeSubscriber
from ..subscriber.external_undivert_subscriber import ExternalUndivertSubscriber
from ..subscriber.host_change_subscriber import HostChangeSubscriber
from ..subscriber.info_task_orchestrator import InfoTaskOrchestrator
from ..subscriber.wireless_reconnect_subscriber import WirelessReconnectSubscriber
from ..subscriber.wireless_status_subscriber import WirelessStatusSubscriber
from ..topic.topic import Topic
from ..util.util import get_system
from .platform_setup import check

log = logging.getLogger(__name__)


def setup_context(args: argparse.Namespace) -> AppContext:
    log.info("CleverSwitch %s starting", __version__)
    check()
    config = _load_config(args)
    shutdown = _setup_shutdown()
    topics = _setup_topics()
    registry = _setup_logi_device_registry()
    _init_subscribers(topics, registry)
    return AppContext(registry, topics, config, shutdown)


def _load_config(args: argparse.Namespace) -> Config:
    try:
        return cfg_module.load(args)
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def _setup_shutdown() -> threading.Event:
    # Graceful shutdown on Ctrl-C / SIGTERM
    shutdown = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: shutdown.set())
    signal.signal(signal.SIGTERM, lambda *_: shutdown.set())
    if get_system() != "Windows":
        signal.signal(signal.SIGHUP, lambda *_: shutdown.set())  # todo not present in windows
        signal.signal(signal.SIGQUIT, lambda *_: shutdown.set())  # todo not present in windows
    return shutdown


def _setup_topics() -> dict[str, Topic]:
    return {
        "event_topic": Topic(),
        "write_topic": Topic(),
        "device_info_topic": Topic(),
        "divert_topic": Topic(),
        "info_progress_topic": Topic(),
    }


def _setup_logi_device_registry() -> LogiDeviceRegistry:
    return LogiDeviceRegistry()


def _init_subscribers(topics: dict[str, Topic], device_registry: LogiDeviceRegistry) -> None:
    DeviceConnectionSubscriber(device_registry, topics)
    DeviceInfoSubscriber(device_registry, topics)
    InfoTaskOrchestrator(device_registry, topics)
    DivertSubscriber(device_registry, topics)
    ExternalUndivertSubscriber(device_registry, topics)
    HostChangeSubscriber(device_registry, topics)
    DivertedHostChangeSubscriber(device_registry, topics)
    WirelessStatusSubscriber(device_registry, topics)
    if get_system() == "Darwin":
        DisconnectPollerSubscriber(device_registry, topics)
        WirelessReconnectSubscriber(device_registry, topics)
