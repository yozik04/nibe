from collections import defaultdict
import logging
from typing import Callable

logger = logging.getLogger("nibe").getChild(__name__)


class EventServer:
    _listeners: defaultdict[str, list[Callable[..., None]]]

    def __init__(self):
        self._listeners = defaultdict(list)

    def notify_event_listeners(self, event_name: str, *args, **kwargs):
        for listener in self._listeners[event_name]:
            try:
                listener(*args, **kwargs)
            except Exception as e:
                logger.exception(e)

    def subscribe(self, event_name: str, callback: Callable[..., None]):
        self._listeners[event_name].append(callback)
