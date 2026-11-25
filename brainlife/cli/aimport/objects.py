"""From the engine's validated output to what is uploaded: the brainlife objects (with the
reviewed plan's datatype mapping), the safety check of the output folder, and the project files."""

import os
import re
import stat

from .chunks import check_chunk_map
from .plan_table import bids_name

# participants.tsv/json go to the participants API, not to project files
PARTICIPANT_FILES = ("participants.tsv", "participants.json")
# electrophysiology objects keep their channels.tsv (bad channels marked in the QA viewer)
# and channels.json inside the object
EPHYS_DATATYPE = re.compile(r"^neuro/(eeg|meg|ieeg)/")
CHANNEL_FILES = (("_channels.tsv", "channels.tsv"), ("_channels.json", "channels.json"))
MICR_DATATYPE = "neuro/ome-zarr"


class RefusedError(Exception):
    pass


def keep_channels(item, entry, manifest, datatype, output_dir):
    """Put the recording's _channels.tsv/_channels.json in an ephys object: under the datatype's
    file of that name (brainlife.io: ``channels`` -> channels.tsv), else as an extra file.
    Returns a note for each extra file."""
    notes = []
    rels = manifest.get(entry.get("id")) or []
    for suffix, name in CHANNEL_FILES:
        rel = next((r for r in rels if isinstance(r, str) and r.endswith(suffix)), None)
        full = os.path.join(output_dir, *rel.split("/")) if rel else None
        if not full or not os.path.exists(full):
            continue
        item["files"][name] = full
        if not any(f.get("filename") == name for f in datatype.get("files") or []):
            notes.append("%s kept with %s as an extra file (%s has no %s file)" % (
                name, bids_name(entry), datatype.get("name"), name))
    return notes


def apply_plan(bids, plan, manifest, datatypes_by_name, output_dir):
    """Apply each plan entry's brainlife datatype and tags to the walked object holding its files.
    -> (datasets, warnings, notes). An entry mapped to an unregistered (draft) datatype keeps its
    object out: its files go to project files."""
    output_dir = os.path.abspath(output_dir)
    entry_by_path = {}
    for entry in plan.get("entries") or []:
        for rel in manifest.get(entry.get("id")) or []:
            entry_by_path[os.path.join(output_dir, *rel.split("/"))] = entry
    datasets, warnings, notes = [], [], []
    for item in bids["datasets"]:
        entry = None
        for full in item["files"].values():
            entry = entry_by_path.get(os.path.abspath(full))
            if entry:
                break
        if entry and entry.get("brainlife_datatype"):
            name = entry["brainlife_datatype"]
            if name not in datatypes_by_name:
                warnings.append("%s is not a registered brainlife datatype (draft): %s goes to project files only"
                                % (name, bids_name(entry)))
                continue
            item["dataset"]["datatype"] = name
            item["dataset"]["datatype_tags"] = list(entry.get("brainlife_tags") or [])
            if EPHYS_DATATYPE.match(name):
                notes += keep_channels(item, entry, manifest, datatypes_by_name[name], output_dir)
        datasets.append(item)
    return datasets, warnings, notes


def micr_datasets(bids_dir, plan, manifest, datatypes_by_name):
    """One object per written .ome.zarr of a micr entry (the walker does not know micr/).
    -> (datasets, warnings, held); held: stores not uploaded (no registered datatype), kept out of
    project files too (a reference store without its chunks is of no use there)."""
    root = os.path.abspath(bids_dir)
    datasets, warnings, held = [], [], []
    for entry in plan.get("entries") or []:
        if entry.get("modality") != "micr" or entry.get("exclude"):
            continue
        for rel in manifest.get(entry.get("id")) or []:
            if not isinstance(rel, str) or not rel.endswith(".ome.zarr"):
                continue
            full = os.path.join(root, *rel.split("/"))
            desc = rel.rsplit("/", 1)[-1]
            name = entry.get("brainlife_datatype") or MICR_DATATYPE
            datatype = datatypes_by_name.get(name)
            first = (datatype.get("files") or [None])[0] if datatype else None
            file_name = first and (first.get("dirname") or first.get("filename") or first.get("id"))
            if not file_name:
                warnings.append("%s%s: %s is not uploaded" % (
                    name, " has no file definition" if datatype else " is not a registered brainlife datatype", desc))
                held.append(full)
                continue
            meta = {"subject": entry.get("subject")}
            if entry.get("session"):
                meta["session"] = entry["session"]
            sample = (entry.get("entities") or {}).get("sample")
            if sample:
                meta["sample"] = sample
            datasets.append({
                "dataset": {"datatype": name, "desc": desc, "datatype_tags": list(entry.get("brainlife_tags") or []),
                            "tags": [], "meta": meta},
                "files": {file_name: full},
            })
    return datasets, warnings, held


def preflight(output_dir, chunk_map=None, manifest=None, input_dir=None):
    """Whole-output check before anything goes up: no symlinks, nothing that is not a regular file
    or folder, no pseudonym key files, no chunk maps, no sourcedata/. With a chunk map, every array
    must lie inside a written .ome.zarr and every source inside the input folder or at an allowed
    https URL."""
    root = os.path.abspath(output_dir)

    def check(rel):
        full = os.path.join(root, rel) if rel else root
        st = os.lstat(full)
        shown = rel or root
        if stat.S_ISLNK(st.st_mode):
            raise RefusedError("refusing to upload %s: it is a symbolic link" % shown)
        name = os.path.basename(full)
        if rel and name == "sourcedata":
            raise RefusedError("refusing to upload %s (sourcedata never leaves this machine)" % shown)
        if name.endswith(".aimport-key.json"):
            raise RefusedError("refusing to upload %s (key files never leave this machine)" % shown)
        if name.endswith(".chunks.json"):
            raise RefusedError("refusing to upload %s (chunk maps never leave this machine)" % shown)
        if stat.S_ISDIR(st.st_mode):
            for child in sorted(os.listdir(full)):
                check(rel + "/" + child if rel else child)
        elif not stat.S_ISREG(st.st_mode):
            raise RefusedError("refusing to upload %s: not a regular file" % shown)

    if not os.path.isdir(root):
        raise RefusedError("the output folder is missing: %s" % root)
    check("")
    if chunk_map:
        check_chunk_map(root, chunk_map, manifest, input_dir)


def list_files(root, rel=""):
    out = []
    for name in sorted(os.listdir(os.path.join(root, rel) if rel else root)):
        sub = rel + "/" + name if rel else name
        if os.path.isdir(os.path.join(root, sub)):
            out += list_files(root, sub)
        else:
            out.append(sub)
    return out


def project_files(output_dir, datasets, held=()):
    """The output's files that are not in an object (README, sidecars, phenotype/, ...), relative
    and posix; held: more files or folders (full paths) kept out."""
    root = os.path.abspath(output_dir)
    files = list_files(root)
    for f in files:
        if re.search(r"(^|/)sourcedata/", f) or f.endswith(".aimport-key.json"):
            raise RefusedError("refusing to upload %s (sourcedata and key files never leave this machine)" % f)
    used = []
    for item in datasets:
        for full in item["files"].values():
            used.append(os.path.relpath(os.path.abspath(full), root).replace(os.sep, "/"))
    used += [os.path.relpath(os.path.abspath(full), root).replace(os.sep, "/") for full in held]
    return [f for f in files if f not in PARTICIPANT_FILES and not any(f == u or f.startswith(u + "/") for u in used)]


def local_bytes(root, rels):
    total = 0
    for rel in rels:
        full = os.path.join(root, rel)
        if os.path.isdir(full) and not os.path.islink(full):
            for dirpath, _dirs, names in os.walk(full):
                for n in names:
                    p = os.path.join(dirpath, n)
                    if os.path.isfile(p) and not os.path.islink(p):
                        total += os.path.getsize(p)
        elif os.path.isfile(full):
            total += os.path.getsize(full)
    return total
