"""TaskIQ broker and scheduler.

Workers are started via `taskiq worker src.workers:broker`. We import
all task modules here so the worker registers them on startup.
"""

from __future__ import annotations

from taskiq import TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from src.core.config import get_settings

_settings = get_settings()

broker = ListQueueBroker(
    url=_settings.redis_url_taskiq,
).with_result_backend(
    RedisAsyncResultBackend(redis_url=_settings.redis_url_taskiq),
)

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)


# IMPORTANT: import task modules AFTER broker is defined so they can
# register themselves via @broker.task. Order doesn't matter functionally,
# but keep alphabetical for readability.
def _register_tasks() -> None:
    from src.workers import notifications  # noqa: F401
    from src.workers import issue_lifecycle  # noqa: F401
    from src.workers import retention  # noqa: F401
    from src.workers import webhook_delivery  # noqa: F401


_register_tasks()
