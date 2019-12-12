from __future__ import annotations
from beginner.exceptions import BeginnerException
from beginner.models.scheduler import Scheduler
from beginner.tags import build_tag_set, fetch_tags
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, AnyStr, Callable, Dict, Set, Union
import asyncio
import math
import pickle


def initialize_scheduler():
    """ Loads scheduler tasks from the database and schedules them to run. """
    for task in Scheduler.select():
        asyncio.create_task(_schedule(task, pickle.loads(task.payload.encode())))


def schedule(
    name: AnyStr,
    when: Union[datetime, timedelta],
    callback_tag: Union[AnyStr, Callable],
    *args,
    **kwargs,
):
    """ Schedule a task to be run and save it to the database. """
    tags = build_tag_set(callback_tag)  # Get tags into a set
    # We don't want the "schedule" tag which is required for all tasks
    if "schedule" in tags:
        tags.remove("schedule")
    when = datetime.now() + when if isinstance(when, timedelta) else when
    time = _seconds_until_run(when)
    payload = {"args": args, "kwargs": kwargs}
    if time <= 0:
        raise TaskScheduledForPast(
            f"Task {name} was scheduled for {when} which was {time} seconds ago"
        )
    task = _schedule_save(name, when, tags, pickle.dumps(payload, 0).decode())
    asyncio.get_event_loop().create_task(_schedule(task, payload))


async def _schedule(task: Scheduler, payload: Dict):
    """ Schedules a task and calls the """
    time = _seconds_until_run(task.when)
    print(f"SCHEDULER: Scheduling {task.name} for {task.when}")
    if time > 0:
        await asyncio.sleep(time)
    print(f"SCHEDULER: Triggering {task.name} running callbacks tagged {task.tag}")
    await _trigger_task(task, payload)


def _schedule_save(
    name: AnyStr, when: datetime, tags: Set, payload: AnyStr
) -> Scheduler:
    """ Takes task parameters and creates a Scheduler row in the database. """
    tag = ",".join(map(str, tags))  # Convert the tag set to a string
    task = Scheduler(name=name, when=when, tag=tag, payload=payload)
    task.save()
    print(f"SCHEDULER: Saved {task.name} for {task.when}")
    return task


def _seconds_until_run(when: datetime) -> int:
    return math.floor((when - datetime.now()).total_seconds())


async def _trigger_task(task: Scheduler, payload: Any):
    """ Runs the callbacks tagged for this task and removes the task from the database. """
    try:
        await _run_tags(set(task.tag.split(",")), payload)
    finally:
        task.delete_instance()


async def _run_tags(tags: Set, payload: Dict):
    """ Runs all callbacks with the appropriate tags. """
    for callback in fetch_tags("schedule", tags):
        if asyncio.iscoroutine(callback) or asyncio.iscoroutinefunction(callback):
            await callback(*payload["args"], **payload["kwargs"])
        else:
            callback(*payload["args"], **payload["kwargs"])


class TaskScheduledForPast(BeginnerException):
    pass


class TaskCallbackMissingSchedulerTag(BeginnerException):
    pass
