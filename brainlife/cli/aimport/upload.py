"""Upload of the objects: each one is a tar.gz streamed into an app-noop task's folder, then
registered in the project. Folders that hold referenced Zarr arrays get their chunks streamed
from the chunk map's sources into the same tar, one at a time; no chunk is written to disk and
the whole archive is never held in memory."""

import os
import queue
import tarfile
import threading
import time

import requests

from . import brainlife_api as bl
from .chunks import arrays_under, chunk_keys, open_source as default_open_source

# BIDS entities that make an object unique, besides subject and session
ENTITIES = ("task", "acq", "ce", "rec", "dir", "run", "mod", "echo", "flip", "inv", "mt", "part",
            "recording", "proc", "split")
BLOCK = 256 * 1024
QUEUE_BLOCKS = 16  # at most ~4 MiB of compressed archive waits for the network


class _Cancelled(Exception):
    pass


class _QueueWriter:
    """A write-only file for tarfile: hands each write to the consumer through a bounded queue."""

    def __init__(self, q, cancelled):
        self.q = q
        self.cancelled = cancelled
        self.buf = bytearray()
        self.sent = 0

    def write(self, data):
        self.buf += data
        while len(self.buf) >= BLOCK:
            self._put(bytes(self.buf[:BLOCK]))
            del self.buf[:BLOCK]
        return len(data)

    def flush(self):
        if self.buf:
            self._put(bytes(self.buf))
            self.buf.clear()

    def _put(self, block):
        while True:
            if self.cancelled.is_set():
                raise _Cancelled()
            try:
                self.q.put(block, timeout=0.5)
                self.sent += len(block)
                return
            except queue.Full:
                continue

    def close(self):
        self.flush()


def _tarinfo(name, size, mtime, mode=0o644):
    ti = tarfile.TarInfo(name)
    ti.size = size
    ti.mtime = int(mtime)
    ti.mode = mode
    ti.uid = ti.gid = 0
    ti.uname = ti.gname = ""  # the local user name stays local
    return ti


def write_archive(item, fileobj, chunk_map=None, open_source=default_open_source, log=print):
    """Write the object's tar.gz to fileobj: its files, then the chunks of the referenced arrays
    inside its folders (a chunk missing at its source is the fill value and is skipped)."""
    refs = []
    with tarfile.open(fileobj=fileobj, mode="w|gz", format=tarfile.GNU_FORMAT) as tar:
        for name, full in item["files"].items():
            if os.path.isdir(full):
                for dirpath, dirs, names in os.walk(full):
                    dirs.sort()
                    for n in sorted(names):
                        path = os.path.join(dirpath, n)
                        sub = os.path.relpath(path, full).replace(os.sep, "/")
                        _add_file(tar, path, name + "/" + sub)
                refs += [(name, sub, meta) for sub, meta in arrays_under(chunk_map, full)]
            else:
                _add_file(tar, os.path.realpath(full), name)
        for name, sub, meta in refs:
            streamed = missing = 0
            for key in chunk_keys(meta):
                chunk = open_source(meta["source"], key, input_dir=chunk_map["input_dir"])
                if chunk is None:
                    missing += 1
                    continue
                try:
                    # addfile copies exactly chunk.size bytes; a short read raises
                    tar.addfile(_tarinfo("%s/%s/%s" % (name, sub, key), chunk.size, chunk.mtime), chunk)
                finally:
                    chunk.close()
                streamed += 1
            # the array path is BIDS-named (no identifiers); its source is never printed
            log("streamed %d chunk(s) of %s/%s%s" % (streamed, name, sub,
                " (%d missing at the source: fill value)" % missing if missing else ""))


def _add_file(tar, path, arcname):
    st = os.stat(path)
    with open(path, "rb") as f:
        tar.addfile(_tarinfo(arcname, st.st_size, st.st_mtime), f)


def stream_archive(item, chunk_map=None, open_source=default_open_source, log=print, progress=None):
    """-> (generator of tar.gz blocks, cancel()). The archive is built in a thread and handed
    over through a bounded queue; an error while building is raised by the generator, so the
    upload fails instead of sending a short object."""
    q = queue.Queue(maxsize=QUEUE_BLOCKS)
    cancelled = threading.Event()
    done = object()
    failure = []

    def produce():
        writer = _QueueWriter(q, cancelled)
        try:
            write_archive(item, writer, chunk_map, open_source, log)
            writer.flush()
        except _Cancelled:
            return
        except BaseException as err:  # handed to the consumer
            failure.append(err)
        while not cancelled.is_set():
            try:
                q.put(done, timeout=0.5)
                return
            except queue.Full:
                continue

    thread = threading.Thread(target=produce, daemon=True)
    thread.start()

    def blocks():
        sent = 0
        last = time.monotonic()
        while True:
            block = q.get()
            if block is done:
                if failure:
                    raise failure[0]
                return
            sent += len(block)
            if progress and time.monotonic() - last >= 5:
                last = time.monotonic()
                progress(sent)
            yield block

    def cancel():
        cancelled.set()
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass
        thread.join(5)

    return blocks(), cancel


def item_key(project_id, datatype_id, dataset):
    meta = dataset.get("meta") or {}
    find = {"project": project_id, "removed": False, "datatype": datatype_id, "desc": dataset.get("desc"),
            "meta.subject": meta.get("subject")}
    if meta.get("session"):
        find["meta.session"] = meta["session"]
    for e in ENTITIES:
        if meta.get(e):
            find["meta." + e] = meta[e]
    return find


def upload_datasets(headers, project, datasets, tags=(), api=None, log=print, chunk_map=None,
                    open_source=default_open_source, poll=3.0):
    """Upload each object unless the project already has it. -> (uploaded descs, skipped descs)."""
    api = api or bl.default_api()
    instance = bl.find_or_create_instance(headers, "upload.%s" % project["group_id"], project, api)
    ids = {d["name"]: d["_id"] for d in bl.all_datatypes(headers, api)}
    uploaded, skipped = [], []
    for item in datasets:
        dataset = item["dataset"]
        desc = dataset.get("desc")
        datatype_id = ids.get(dataset["datatype"])
        if datatype_id is None:
            raise bl.ApiError("%s is not a datatype on brainlife.io" % dataset["datatype"])
        if bl.count_datasets(headers, item_key(project["_id"], datatype_id, dataset), api) > 0:
            log("%s: already in the project, skipped" % desc)
            skipped.append(desc)
            continue
        log("uploading %s (%s)" % (desc, dataset["datatype"]))
        task = bl.submit_noop(headers, instance, datatype_id, dataset, api)
        bl.wait_task(headers, task["_id"], api, poll)
        blocks, cancel = stream_archive(item, chunk_map, open_source, log,
                                        progress=lambda n: log("  uploading .. %.1f MB" % (n / 2 ** 20)))
        try:
            res = requests.post(api["amaretti"] + "/task/upload/" + task["_id"],
                                params={"p": "upload.tar.gz", "untar": "true"},
                                data=blocks, headers=headers, timeout=(60, 3600))
        finally:
            cancel()
        if res.status_code != 200:
            raise bl.ApiError("upload of %s failed with status %d" % (desc, res.status_code))
        all_tags = list(dict.fromkeys(list(tags) + list(dataset.get("tags") or [])))
        registered = bl.register_dataset(headers, project["_id"], task["_id"], dataset, all_tags, api)
        log("  registered object %s" % registered.get("_id"))
        uploaded.append(desc)
    return uploaded, skipped


def update_participants(headers, project, bids, api=None, log=print):
    log("updating participants/column data")
    bl.update_participants(headers, project["_id"], bids["participants"], bids["participants_json"],
                           api or bl.default_api())


def upload_project_files(headers, project, output_dir, files, api=None):
    api = api or bl.default_api()
    for rel in files:
        path = os.path.join(output_dir, *rel.split("/"))
        bl.upload_project_file(headers, project["_id"], rel, path, os.path.getsize(path), api)
