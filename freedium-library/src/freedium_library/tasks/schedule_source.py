"""Custom ScheduleSource that reads scheduled tasks from the broker's
in-memory task registry instead of Redis.

The deprecated RedisScheduleSource stores schedules via async add_schedule,
which is never awaited at import time → schedules silently disappear.
This source reads directly from broker.get_all_tasks(), where the
@broker.task(schedule=[...]) decorator stored the schedule in labels.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from taskiq.abc.schedule_source import ScheduleSource
from taskiq.scheduler.scheduled_task import ScheduledTask

if TYPE_CHECKING:
    from taskiq.abc.broker import AsyncBroker


class BrokerScheduleSource(ScheduleSource):
    """Schedule source backed by the broker's in-memory task registry.
    No Redis dependency for schedules. Reads once at startup."""

    def __init__(self, broker: "AsyncBroker"):
        self._broker = broker

    async def get_schedules(self) -> list[ScheduledTask]:
        tasks: list[ScheduledTask] = []
        for _name, task in self._broker.get_all_tasks().items():
            for entry in task.labels.get("schedule") or []:
                tasks.append(
                    ScheduledTask(
                        task_name=task.task_name,
                        labels=task.labels,
                        cron=entry.get("cron"),
                        cron_offset=entry.get("cron_offset"),
                        time=entry.get("time"),
                        interval=entry.get("interval"),
                        args=entry.get("args", []),
                        kwargs=entry.get("kwargs", {}),
                        schedule_id=f"{task.task_name}:{entry}",
                    )
                )
        return tasks

    async def add_schedule(self, schedule: ScheduledTask) -> None:
        pass  # no-op: schedules live on the broker, we read them every cycle

    async def startup(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass
