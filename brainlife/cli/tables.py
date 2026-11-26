"""Project tables (warehouse /table API): BIDS tables that describe subjects, sessions or files
(phenotype/*.tsv, samples.tsv, sessions and scans tables) and any other table organized like
participants.tsv. participants.tsv itself goes to the participants API, not here.

Finding the tables follows the warehouse (api/controllers/table.helpers.js): same files, same
sidecar inheritance. Per-subject sessions/scans files are sent as one table each, with
participant_id (and session_id for scans) columns added from their folders, because the upload
API links rows to subjects and sessions through those columns.
"""

import json
import os
import re

import requests

# the warehouse accepts JSON bodies up to 2MB
MAX_BODY = 1900 * 1024


class TableApiMissing(Exception):
    """The brainlife.io instance has no /table API yet."""


def classify(rel):
    """{"kind", "name", "subject"?, "session"?} for a BIDS table path, or None."""
    if rel == "participants.tsv":
        return {"kind": "participants", "name": "participants"}
    if rel == "samples.tsv":
        return {"kind": "samples", "name": "samples"}
    m = re.match(r"^phenotype/([^/]+)\.tsv$", rel)
    if m:
        return {"kind": "phenotype", "name": "phenotype/" + m.group(1)}
    m = re.match(r"^sub-([^/_]+)/sub-([^/_]+)_sessions\.tsv$", rel)
    if m and m.group(1) == m.group(2):
        return {"kind": "sessions", "name": "sessions", "subject": m.group(1)}
    m = re.match(r"^sub-([^/_]+)/sub-([^/_]+)_scans\.tsv$", rel)
    if m and m.group(1) == m.group(2):
        return {"kind": "scans", "name": "scans", "subject": m.group(1)}
    m = re.match(r"^sub-([^/_]+)/ses-([^/_]+)/sub-([^/_]+)_ses-([^/_]+)_scans\.tsv$", rel)
    if m and m.group(1) == m.group(3) and m.group(2) == m.group(4):
        return {"kind": "scans", "name": "scans", "subject": m.group(1), "session": m.group(2)}
    return None


def sidecar_candidates(rel):
    """Sidecars that apply to a table in BIDS inheritance order (root first, fewest entities
    first); later ones override earlier ones."""
    parts = rel.split("/")
    name = parts.pop()
    m = re.match(r"^((?:[a-z]+-[^_]+_)+)?([a-z]+)\.tsv$", name, re.I)
    entities = m.group(1)[:-1].split("_") if m and m.group(1) else []
    if not m or not entities:
        return [re.sub(r"\.tsv$", ".json", rel)]
    suffix = m.group(2)
    subsets = [[]]
    for e in entities:
        subsets += [s + [e] for s in list(subsets)]
    subsets.sort(key=len)
    out = []
    for depth in range(len(parts) + 1):
        prefix = "".join(p + "/" for p in parts[:depth])
        out += [prefix + "_".join(s + [suffix]) + ".json" for s in subsets]
    return out


def find_table_files(root):
    def ls(d):
        try:
            return sorted(os.listdir(d))
        except OSError:
            return []

    files = []
    if "samples.tsv" in ls(root):
        files.append("samples.tsv")
    files += ["phenotype/" + n for n in ls(os.path.join(root, "phenotype")) if n.endswith(".tsv")]
    for sub in [n for n in ls(root) if n.startswith("sub-")]:
        for n in ls(os.path.join(root, sub)):
            if n.endswith("_sessions.tsv") or n.endswith("_scans.tsv"):
                files.append(sub + "/" + n)
            if n.startswith("ses-"):
                files += [sub + "/" + n + "/" + s for s in ls(os.path.join(root, sub, n)) if s.endswith("_scans.tsv")]
    return [f for f in files if classify(f)]


def _sidecar(root, rel, warnings):
    merged = {}
    for jrel in sidecar_candidates(rel):
        path = os.path.join(root, jrel)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                merged.update(json.load(f))
        except (OSError, ValueError):
            warnings.append(jrel + ": sidecar json could not be parsed")
    return merged


def _parse_tsv(text):
    lines = [line.rstrip("\r") for line in text.split("\n") if line.strip()]
    if not lines:
        return [], []
    header = [h.strip() for h in lines[0].split("\t")]
    rows = []
    for line in lines[1:]:
        cells = line.split("\t")
        rows.append([(cells[i] if i < len(cells) else "").strip() for i in range(len(header))])
    return header, rows


def collect_tables(root):
    """BIDS tables under root as upload bodies [{"name", "kind", "tsv", "json"}], and warnings.
    participants.tsv is left out (it has its own API)."""
    warnings = []
    single = []
    combined = {}
    for rel in find_table_files(root):
        info = classify(rel)
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                text = f.read()
        except OSError as err:
            # an unfetched git-annex file is a broken symlink
            warnings.append("%s: can not be read (%s)" % (rel, err.strerror))
            continue
        sidecar = _sidecar(root, rel, warnings)
        if info["kind"] in ("sessions", "scans"):
            t = combined.setdefault(info["name"], {"kind": info["kind"], "header": [], "rows": [], "sidecar": {}})
            header, rows = _parse_tsv(text)
            ids = ["participant_id"] + (["session_id"] if info["kind"] == "scans" else [])
            for col in ids + header:
                if col not in t["header"]:
                    t["header"].append(col)
            for row in rows:
                values = dict(zip(header, row))
                values.setdefault("participant_id", "sub-" + info["subject"])
                if info.get("session"):
                    values.setdefault("session_id", "ses-" + info["session"])
                t["rows"].append(values)
            for k, v in sidecar.items():
                t["sidecar"].setdefault(k, v)
        else:
            header = _parse_tsv(text)[0]
            columns = {k: v for k, v in sidecar.items() if isinstance(v, dict) and k in header}
            single.append({"name": info["name"], "kind": info["kind"], "tsv": text,
                           "json": json.dumps(columns) if columns else None})
    for name, t in combined.items():
        lines = ["\t".join(t["header"])] + ["\t".join(r.get(c, "") for c in t["header"]) for r in t["rows"]]
        columns = {k: v for k, v in t["sidecar"].items() if isinstance(v, dict) and k in t["header"]}
        single.append({"name": name, "kind": t["kind"], "tsv": "\n".join(lines) + "\n",
                       "json": json.dumps(columns) if columns else None})
    return single, warnings


def _check(res, what):
    # a warehouse without the route answers with express' default page ("Cannot PUT /table/..");
    # a missing project or table is an empty 404
    if res.status_code == 404 and "Cannot " in res.text:
        raise TableApiMissing()
    if res.status_code != 200:
        try:
            msg = res.json().get("message")
        except Exception:
            msg = None
        raise RuntimeError("%s failed (HTTP %d)%s" % (what, res.status_code, ": " + str(msg) if msg else ""))
    return res.json()


def put_table(headers, project_id, table, warehouse):
    body = {k: v for k, v in table.items() if v is not None}
    res = requests.put(warehouse + "/table/" + project_id, headers=headers, json=body, timeout=300)
    return _check(res, "uploading table " + table["name"])


def list_tables(headers, project_id, warehouse):
    return _check(requests.get(warehouse + "/table/" + project_id, headers=headers, timeout=60), "listing tables")


def get_table(headers, project_id, table_id, warehouse, page=5000):
    """(table, rows) - every row, read page by page."""
    rows = []
    table = None
    while True:
        res = requests.get(warehouse + "/table/%s/%s" % (project_id, table_id), headers=headers,
                           params={"skip": len(rows), "limit": page}, timeout=120)
        data = _check(res, "reading table " + table_id)
        table = data["table"]
        rows += data["rows"]
        if len(data["rows"]) < page:
            return table, rows


def remove_table(headers, project_id, table_id, warehouse):
    res = requests.delete(warehouse + "/table/%s/%s" % (project_id, table_id), headers=headers, timeout=60)
    return _check(res, "removing table " + table_id)


def rows_to_tsv(table, rows):
    order = list(table.get("column_order") or [])
    for r in rows:
        for k in r.get("values") or {}:
            if k not in order:
                order.append(k)
    lines = ["\t".join(order)] + ["\t".join(str((r.get("values") or {}).get(c, "")) for c in order) for r in rows]
    return "\n".join(lines) + "\n"


def upload_tables(headers, project, bids_dir, api, log=print):
    """Send the BIDS tables under bids_dir to the project's tables. Returns how many were sent.
    The files themselves still go up as project files (aimport) - this adds the table rows."""
    tables, warnings = collect_tables(bids_dir)
    for w in warnings:
        log("! table " + w)
    sent = 0
    for t in tables:
        size = len(json.dumps(t))
        if size > MAX_BODY:
            log("! table %s is too large for the table API (%d bytes); it stays a project file only" % (t["name"], size))
            continue
        try:
            put_table(headers, project["_id"], t, api["warehouse"])
        except TableApiMissing:
            log("! this brainlife.io has no table API yet; the tables stay project files only")
            return sent
        except Exception as err:
            # the data objects are already uploaded: report the table and go on
            log("! table %s was not uploaded: %s" % (t["name"], err))
            continue
        sent += 1
    return sent
