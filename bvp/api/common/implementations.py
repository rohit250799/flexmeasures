from datetime import datetime

import pytz
from flask import request, current_app
from flask_json import as_json

from bvp.data.config import db
from bvp.data.models.task_runs import LatestTaskRun


@as_json
def ping():
    return dict(message="ok"), 200


@as_json
def get_task_run():
    """
    Get latest task runs.
    This endpoint returns output conforming to the task monitoring tool (TODO: actual name)
    """
    task_name: str = request.args.get("name")
    frequency = current_app.config.get("MONITOR_FREQUENCY_%s" % task_name.upper(), 10)
    if task_name is None or task_name == "":
        return (
            {
                "status": "ERROR",
                "reason": "No task name given.",
                "lastrun": datetime(1970, 1, 1),
                "frequency": frequency,
            },
            400,
        )

    last_run = LatestTaskRun.query.filter(LatestTaskRun.name == task_name).first()
    if not last_run:
        return (
            {
                "status": "ERROR",
                "reason": "Task %s has no last run time." % task_name,
                "lastrun": datetime(1970, 1, 1),
                "frequency": frequency,
            },
            400,
        )
    status = "OK" if last_run.status else "ERROR"
    return dict(lastrun=last_run.datetime, status=status, frequency=frequency)


@as_json
def post_task_run():
    """
    Post that a task has been (attempted to) run.
    Form fields to send in: name: str, status: bool [defaults to True], datetime: datetime [defaults to now]
    """
    task_name = request.form.get("name", "")
    if task_name == "":
        return {"status": "ERROR", "reason": "No task name given."}, 400
    date_time = request.form.get("datetime", datetime.utcnow().replace(tzinfo=pytz.utc))
    status = request.form.get("status", "True") == "True"
    try:
        task_run = LatestTaskRun.query.filter(
            LatestTaskRun.name == task_name
        ).one_or_none()
        if task_run is None:
            task_run = LatestTaskRun(name=task_name)
            db.session.add(task_run)
        task_run.datetime = date_time
        task_run.status = status
        db.session.commit()  # TODO: should we strive to have only one commit per request?
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}, 500
    return {"status": "OK"}, 200