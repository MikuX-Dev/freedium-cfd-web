"""TaskIQ broker + background tasks for Freedium.

The broker connects to Redis and dispatches async tasks to worker
processes. Tasks here are designed to be fire-and-forget from the
request handler — failures are logged but never propagate to the user.

A RedisAsyncResultBackend is configured so callers can wait for results
via task.wait_result() or poll via result_backend.get_result(task_id).
"""
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend
from taskiq import TaskiqScheduler
import os

from freedium_library.tasks.schedule_source import BrokerScheduleSource

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

result_backend = RedisAsyncResultBackend(
    redis_url=REDIS_URL,
    keep_results=True,
)

broker = ListQueueBroker(url=REDIS_URL).with_result_backend(result_backend)

# BrokerScheduleSource reads scheduled tasks directly from the broker's
# in-memory registry (where @broker.task(schedule=[...]) stores them in
# labels). The deprecated RedisScheduleSource tried to write schedules
# via async add_schedule, which was never awaited at import time →
# schedules silently never landed.
scheduler = TaskiqScheduler(
    broker=broker,
    sources=[BrokerScheduleSource(broker)],
)

# Import task submodules so they register with the broker on worker startup.
# This must come AFTER broker is defined (tasks reference it).
from freedium_library.tasks import cache as _cache  # noqa: E402, F401
from freedium_library.tasks import random_posts as _random_posts  # noqa: E402, F401
from freedium_library.tasks import article_count as _article_count  # noqa: E402, F401
from freedium_library.tasks import image_converter as _image_converter  # noqa: E402, F401
