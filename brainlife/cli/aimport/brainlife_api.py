"""The brainlife.io calls bl aimport makes (warehouse and amaretti), as plain dicts.

``api`` is {"warehouse": url, "amaretti": url}; by default pybrainlife's configured services
(``bl -H <host>``). ``headers`` carries the user's JWT.
"""

import json
import re
import time

import requests

from ...api.api import services

OBJECT_ID = re.compile(r"[0-9a-fA-F]{24}")


def default_api():
    return {"warehouse": services["warehouse"], "amaretti": services["amaretti"], "main": services["main"]}


class ApiError(Exception):
    pass


def _check(res, what):
    if res.status_code != 200:
        try:
            msg = res.json().get("message")
        except Exception:
            msg = None
        raise ApiError("%s failed (HTTP %d)%s" % (what, res.status_code, ": " + str(msg) if msg else ""))
    return res.json()


def project_by_id(headers, project_id, api):
    res = requests.get(api["warehouse"] + "/project", headers=headers, params={
        "find": json.dumps({"_id": project_id, "removed": False}), "limit": 1}, timeout=60)
    projects = _check(res, "looking up the project").get("projects") or []
    return projects[0] if len(projects) == 1 else None


def all_datatypes(headers, api):
    res = requests.get(api["warehouse"] + "/datatype", headers=headers, params={"limit": 0, "skip": 0}, timeout=60)
    return _check(res, "reading the datatypes").get("datatypes") or []


def project_subjects(headers, project_id, api, limit=1000):
    """Subjects and sessions already in the project, so the engine does not reuse their IDs."""
    subjects = []
    sessions = {}
    skip = 0
    while True:
        res = requests.get(api["warehouse"] + "/dataset", headers=headers, params={
            "find": json.dumps({"project": project_id, "removed": False}),
            # the warehouse checks each row's project, so it must be selected (without it the
            # request fails on the server and never answers)
            "select": "meta.subject meta.session project",
            "sort": "_id",  # a stable order, so paging does not skip or repeat
            "limit": limit, "skip": skip}, timeout=120)
        body = _check(res, "reading the project's subjects")
        page = body.get("datasets") or []
        for d in page:
            meta = d.get("meta") or {}
            sub = meta.get("subject")
            if sub is None or sub == "":
                continue
            sub = str(sub)
            if sub not in subjects:
                subjects.append(sub)
            ses = meta.get("session")
            if ses is not None and ses != "":
                lst = sessions.setdefault(sub, [])
                if str(ses) not in lst:
                    lst.append(str(ses))
        skip += len(page)
        if len(page) < limit or skip >= (body.get("count") or 0):
            break
    return {"existing_subjects": subjects, "existing_sessions": sessions}


def find_or_create_instance(headers, name, project, api):
    res = requests.get(api["amaretti"] + "/instance", headers=headers,
                       params={"find": json.dumps({"name": name}), "limit": 1}, timeout=60)
    instances = _check(res, "looking up the upload instance").get("instances") or []
    if instances:
        return instances[0]
    res = requests.post(api["amaretti"] + "/instance", headers=headers, timeout=60, json={
        "name": name, "config": {"brainlife": True}, "group_id": project["group_id"]})
    return _check(res, "creating the upload instance")


def submit_noop(headers, instance, datatype_id, dataset, api):
    """An app-noop task whose output is the new object; the upload goes into its folder."""
    res = requests.post(api["amaretti"] + "/task", headers=headers, timeout=60, json={
        "instance_id": instance["_id"],
        "name": instance.get("name"),
        "service": "brainlife/app-noop",
        "max_runtime": 600 * 1000,
        "config": {"_outputs": [{
            "id": "output",
            "datatype": datatype_id,
            "datatype_tags": dataset.get("datatype_tags") or [],
            "meta": dataset.get("meta") or {},
        }]},
    })
    return _check(res, "submitting the upload task")["task"]


def wait_task(headers, task_id, api, poll=3.0):
    while True:
        res = requests.get(api["amaretti"] + "/task", headers=headers,
                           params={"find": json.dumps({"_id": task_id})}, timeout=60)
        tasks = _check(res, "reading the upload task").get("tasks") or []
        if len(tasks) == 1:
            if tasks[0].get("status") == "finished":
                return tasks[0]
            if tasks[0].get("status") == "failed":
                raise ApiError("the upload task failed: %s" % tasks[0].get("status_msg"))
        time.sleep(poll)


def count_datasets(headers, find, api):
    res = requests.get(api["warehouse"] + "/dataset", headers=headers,
                       params={"find": json.dumps(find), "limit": 0}, timeout=60)
    return _check(res, "looking for the object in the project").get("count") or 0


def register_dataset(headers, project_id, task_id, dataset, tags, api):
    res = requests.post(api["warehouse"] + "/dataset", headers=headers, timeout=120, json={
        "project": project_id, "task_id": task_id, "output_id": "output",
        "meta": dataset.get("meta") or {}, "desc": dataset.get("desc"), "tags": tags})
    return _check(res, "registering the object")


def update_participants(headers, project_id, participants, columns, api):
    res = requests.put(api["warehouse"] + "/participant/" + project_id, headers=headers, timeout=120,
                       json={"subjects": participants, "columns": columns})
    _check(res, "updating the participants table")


def upload_project_file(headers, project_id, rel, path, size, api, prefix="bids/"):
    res = requests.post(api["warehouse"] + "/files/%s/upload/presigned" % project_id, headers=headers, timeout=60,
                        json={"fileName": rel, "fileSize": size, "contentType": "application/octet-stream",
                              "prefix": prefix})
    url = _check(res, "asking where to upload " + rel)["presignedUrl"]
    # the presigned URL carries its own credentials: no Authorization header
    with open(path, "rb") as f:
        put = requests.put(url, data=f, headers={"Content-Length": str(size)}, timeout=(60, 600))
    if put.status_code < 200 or put.status_code >= 300:
        raise ApiError("upload of %s failed with status %d" % (rel, put.status_code))
