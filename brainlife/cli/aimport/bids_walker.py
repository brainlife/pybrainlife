"""Turn a BIDS folder (the engine's output) into brainlife data objects.

walk(root) -> {"participants": [...], "participants_json": {...} | None, "datasets": [item]}
where item = {"dataset": {"datatype", "desc", "datatype_tags", "tags", "meta"},
              "files": {brainlife file name: full path}}.

Sidecar JSON is inherited down the tree (root, subject, session, then the file's own sidecar).
Covered: anat (T1w, T2w, FLAIR, MP2RAGE), dwi, func (bold), fmap (fieldmap, phasediff,
phase1/phase2, pepolar epi, b0 epi with bvec/bval), eeg and meg. Everything else in the folder
goes up as project files (see upload.project_files).
"""

import json
import os

STRUCTURAL = {"sub": "subject", "ses": "session"}


def parse_name(name):
    """sub-01_ses-1_T1w.nii.gz -> {"sub": "01", "ses": "1"}, suffix "T1w.nii.gz"."""
    entities = {}
    suffix = "invalid"
    for part in name.split("_"):
        tokens = part.split("-")
        if len(tokens) == 1:
            suffix = tokens[0]
        else:
            entities[tokens[0]] = "-".join(tokens[1:])
    return entities, suffix


class File:
    def __init__(self, folder, name):
        self.folder = folder
        self.name = name
        self.entities, self.suffix = parse_name(name)

    @property
    def path(self):
        return os.path.join(self.folder, self.name)

    @property
    def stem(self):
        """The name without its suffix: sub-01_task-rest_ for sub-01_task-rest_bold.nii.gz."""
        return self.name[: len(self.name) - len(self.suffix)]

    def meta(self):
        return {STRUCTURAL.get(k, k): v for k, v in self.entities.items()}

    def tags(self):
        return ["%s-%s" % (k, v) for k, v in self.entities.items() if k not in STRUCTURAL]


def _exists(path):
    # a datalad symlink not fetched yet still counts
    return os.path.lexists(path)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def escape_dot(obj):
    """Mongo keys must not contain '.': replace it with '-' at every level."""
    if isinstance(obj, dict):
        for key in list(obj):
            escape_dot(obj[key])
            if "." in key:
                obj[key.replace(".", "-")] = obj.pop(key)
    elif isinstance(obj, list):
        for v in obj:
            escape_dot(v)
    return obj


def parse_participants(text):
    lines = [l.strip() for l in text.strip().split("\n")]
    if not lines or not lines[0]:
        return []
    head = [h.replace(".", "-") for h in lines[0].split("\t")]
    col = 0
    for key in ("Observations", "participant_id"):
        if key in head:
            col = head.index(key)
    out = []
    for row in lines[1:]:
        if not row:
            continue
        cells = row.split("\t")
        subject = cells[col] if col < len(cells) else ""
        if subject.lower().startswith("sub-"):
            subject = subject[4:]
        p = {"subject": subject}
        for i, cell in enumerate(cells):
            if i != col and i < len(head):
                p[head[i]] = cell.strip()
        out.append(escape_dot(p))
    return out


def _listdir(folder):
    try:
        return sorted(n for n in os.listdir(folder) if not n.startswith("."))
    except OSError:
        return []


class Walker:
    def __init__(self, root):
        self.root = root
        self.datasets = []

    def add(self, datatype, desc, files, meta, tags, datatype_tags=()):
        self.datasets.append({
            "dataset": {"datatype": datatype, "desc": desc, "datatype_tags": list(datatype_tags),
                        "tags": list(tags), "meta": meta},
            "files": files,
        })

    # sidecars: {json file name: content}, the deeper level overriding key by key
    @staticmethod
    def level_sidecars(folder, parent):
        sidecars = {k: dict(v) for k, v in parent.items()}
        for name in _listdir(folder):
            if name.endswith(".json") and os.path.isfile(os.path.join(folder, name)):
                sidecars.setdefault(name, {}).update(_read_json(os.path.join(folder, name)))
        return sidecars

    @staticmethod
    def inherited(sidecars, stem, suffix_json):
        """The inherited sidecar of a file: the bare suffix (bold.json), then the same name without
        run-, then without ses-, then without sub- (task-rest_bold.json)."""
        out = dict(sidecars.get(suffix_json, {}))
        tokens = (stem + suffix_json).split("_")
        found = {}
        for strip in ("run-", "ses-", "sub-"):
            tokens = [t for t in tokens if not t.startswith(strip)]
            name = "_".join(tokens)
            if name in sidecars:
                found = dict(sidecars[name], **found)
        out.update(found)
        return out

    def sidecar(self, folder, f, sidecars, suffix_json):
        meta = self.inherited(sidecars, f.stem, suffix_json)
        meta.update(_read_json(os.path.join(folder, f.stem + suffix_json)))
        return meta

    def walk(self):
        root_sidecars = {}
        for name in _listdir(self.root):
            if name.endswith(".json") and os.path.isfile(os.path.join(self.root, name)):
                root_sidecars[name] = _read_json(os.path.join(self.root, name))
        for name in _listdir(self.root):
            full = os.path.join(self.root, name)
            if name.startswith("sub-") and os.path.isdir(full):
                self.level(full, root_sidecars)
        for item in self.datasets:
            escape_dot(item["dataset"]["meta"])
        return self.datasets

    def level(self, folder, parent):
        """A subject or session folder."""
        sidecars = self.level_sidecars(folder, parent)
        handlers = {"anat": self.anat, "dwi": self.dwi, "func": self.func, "fmap": self.fmap,
                    "eeg": self.ephys, "meg": self.ephys}
        for name in _listdir(folder):
            full = os.path.join(folder, name)
            if not os.path.isdir(full):
                continue
            if name.startswith("ses-"):
                self.level(full, sidecars)
            elif name in handlers:
                handlers[name](full, sidecars, name)

    def files(self, folder):
        return [File(folder, n) for n in _listdir(folder)]

    # --- anat ----------------------------------------------------------------------------------

    def anat(self, folder, sidecars, _kind):
        simple = {"T1w": ("neuro/anat/t1w", "t1.nii.gz"), "T2w": ("neuro/anat/t2w", "t2.nii.gz"),
                  "FLAIR": ("neuro/anat/flair", "flair.nii.gz")}
        mp2rage = {}
        for f in self.files(folder):
            base = f.suffix.split(".")[0]
            if base in simple and f.suffix.startswith(base + ".nii"):
                datatype, fname = simple[base]
                meta = self.sidecar(folder, f, sidecars, base + ".json")
                meta.update(f.meta())
                self.add(datatype, f.name, {fname: f.path}, meta, f.tags())
            elif base in ("MP2RAGE", "UNIT1"):
                key = tuple((k, v) for k, v in f.entities.items() if k not in ("inv", "part"))
                mp2rage.setdefault(key, []).append(f)
        for group in mp2rage.values():
            self.mp2rage(folder, sidecars, group)

    def mp2rage(self, folder, sidecars, group):
        images = [f for f in group if f.suffix == "MP2RAGE.nii.gz"]
        if not images:
            return
        first = images[0]
        meta = dict(sidecars.get("MP2RAGE.json", {}))
        meta.update(first.meta())
        tags = []
        files = {}
        for f in group:
            part = f.entities.get("part", "mag")
            inv = f.entities.get("inv")
            if f.suffix == "MP2RAGE.json":
                meta.update(_read_json(f.path))
                tags += [t for t in f.tags() if not t.startswith(("inv-", "part-")) and t not in tags]
                files["%s.inv%s.json" % (part, inv)] = f.path
            elif f.suffix == "MP2RAGE.nii.gz":
                files["%s.inv%s.nii.gz" % (part, inv)] = f.path
            elif f.suffix == "UNIT1.nii.gz":
                files["unit1.nii.gz"] = f.path
            elif f.suffix == "UNIT1.json":
                files["unit1.json"] = f.path
        meta.pop("inv", None)
        meta.pop("part", None)
        self.add("neuro/anat/mp2rage", folder, files, meta, tags)

    # --- dwi / func ----------------------------------------------------------------------------

    def dwi(self, folder, sidecars, _kind):
        for f in self.files(folder):
            if f.suffix not in ("dwi.nii", "dwi.nii.gz"):
                continue
            meta = self.sidecar(folder, f, sidecars, "dwi.json")
            meta.update(f.meta())
            files = {"dwi.nii.gz": f.path, "dwi.bvecs": os.path.join(folder, f.stem + "dwi.bvec"),
                     "dwi.bvals": os.path.join(folder, f.stem + "dwi.bval")}
            for extra in ("sbref.nii.gz", "sbref.json"):
                if _exists(os.path.join(folder, f.stem + extra)):
                    files[extra] = os.path.join(folder, f.stem + extra)
            self.add("neuro/dwi", f.name, files, meta, f.tags())

    def func(self, folder, sidecars, _kind):
        for f in self.files(folder):
            if f.suffix not in ("bold.nii", "bold.nii.gz"):
                continue
            f.entities.setdefault("task", "unknown")
            meta = self.sidecar(folder, f, sidecars, "bold.json")
            meta.update(f.meta())
            files = {"bold.nii.gz": f.path}
            for extra in ("events.tsv", "sbref.nii.gz", "sbref.json", "physio.tsv.gz", "physio.json"):
                if _exists(os.path.join(folder, f.stem + extra)):
                    files[extra] = os.path.join(folder, f.stem + extra)
            self.add("neuro/func/task", f.name, files, meta, f.tags(), [f.entities["task"].lower()])

    # --- fmap ----------------------------------------------------------------------------------

    def fmap(self, folder, sidecars, _kind):
        groups = {}
        for f in self.files(folder):
            key = tuple(f.entities.get(k) for k in ("sub", "ses", "run", "acq"))
            groups.setdefault(key, []).append(f)
        # pepolar runs that share IntendedFor belong to one object
        merged = {}
        for key, group in groups.items():
            intended = None
            if any(f.suffix == "epi.nii.gz" for f in group):
                for f in group:
                    if f.suffix == "epi.json":
                        intended = _read_json(f.path).get("IntendedFor") or intended
            mkey = ("intended", json.dumps(intended, sort_keys=True)) if intended else key
            merged.setdefault(mkey, []).extend(group)
        for group in merged.values():
            suffixes = {f.suffix for f in group}
            if "fieldmap.nii.gz" in suffixes:
                self.fmap_kind(folder, sidecars, group, "fieldmap", "single", ("fieldmap.", "magnitude."))
            if "phasediff.nii.gz" in suffixes:
                self.fmap_kind(folder, sidecars, group, "phasediff", "phasediff", ("phasediff.", "magnitude1.", "magnitude2"))
            if "phase1.nii.gz" in suffixes and "phase2.nii.gz" in suffixes:
                self.fmap_2phase(folder, group)
            if "epi.nii.gz" in suffixes:
                self.fmap_pepolar(folder, sidecars, group)
            if "epi.bvec" in suffixes:
                self.fmap_b0(folder, sidecars, group)

    def fmap_kind(self, folder, sidecars, group, base, tag, prefixes):
        f = next(x for x in group if x.suffix == base + ".nii.gz")
        meta = self.sidecar(folder, f, sidecars, base + ".json")
        meta.update(f.meta())
        files = {x.suffix: x.path for x in group if x.suffix.startswith(prefixes)}
        self.add("neuro/fmap", f.name, files, meta, f.tags(), [tag])

    def fmap_2phase(self, folder, group):
        p1 = next(x for x in group if x.suffix == "phase1.nii.gz")
        p2 = next(x for x in group if x.suffix == "phase2.nii.gz")
        meta = _read_json(os.path.join(folder, p1.stem + "phase1.json"))
        meta.update(_read_json(os.path.join(folder, p2.stem + "phase2.json")))
        meta.update(p1.meta())
        meta.update(p2.meta())
        tags = list(dict.fromkeys(p1.tags() + p2.tags()))
        files = {x.suffix: x.path for x in group if x.suffix.startswith(("phase1.", "phase2.", "magnitude1.", "magnitude2."))}
        self.add("neuro/fmap", p1.name + " and " + p2.name, files, meta, tags, ["2phasemag"])

    def fmap_pepolar(self, folder, sidecars, group):
        dirs = []
        for f in group:
            if f.entities.get("dir") not in dirs:
                dirs.append(f.entities.get("dir"))
        meta = {}
        files = {}
        tags = []
        ent_meta = {}
        first = None
        for f in group:
            n = dirs.index(f.entities.get("dir")) + 1
            if f.suffix == "epi.json":
                meta.update(self.inherited(sidecars, f.stem, "epi.json"))
                meta.update(_read_json(f.path))
                files["epi%d.json" % n] = f.path
            elif f.suffix == "epi.nii.gz":
                files["epi%d.nii.gz" % n] = f.path
                tags += [t for t in f.tags() if t not in tags]
                ent_meta = f.meta()
                first = first or f
        ent_meta.pop("dir", None)
        meta.update(ent_meta)
        self.add("neuro/fmap", first.name if first else folder, files, meta, tags, ["pepolar"])

    def fmap_b0(self, folder, sidecars, group):
        epi = next((x for x in group if x.suffix == "epi.nii.gz"), None)
        bvec = next((x for x in group if x.suffix == "epi.bvec"), None)
        bval = next((x for x in group if x.suffix == "epi.bval"), None)
        if not (epi and bvec and bval):
            return
        meta = self.sidecar(folder, epi, sidecars, "epi.json")
        meta.update(epi.meta())
        files = {"dwi.nii.gz": epi.path, "dwi.bvecs": bvec.path, "dwi.bvals": bval.path}
        tags = ["fmap", "b0"] + ([epi.entities["dir"]] if epi.entities.get("dir") else [])
        self.add("neuro/dwi", epi.name, files, meta, tags)

    # --- eeg / meg -----------------------------------------------------------------------------

    EEG_FORMATS = (("eeg.bdf", "neuro/eeg/bdf"), ("eeg.edf", "neuro/eeg/edf"),
                   ("eeg.eeg", "neuro/eeg/brainvision"), ("eeg.fdt", "neuro/eeg/eeglab"),
                   ("eeg.set", "neuro/eeg/eeglab"))
    MEG_FORMATS = (("meg.ds", "neuro/meg/ctf"), ("meg.fif", "neuro/meg/fif"))
    SHARED = ("coordsystem.json", "electrodes.tsv", "headshape.pos")

    def ephys(self, folder, sidecars, kind):
        """One object per recording (files grouped by all their entities); the folder's shared
        files (coordsystem, electrodes, headshape; MEG calibration and crosstalk) go with each."""
        groups = {}
        for f in self.files(folder):
            key = "_".join("%s-%s" % kv for kv in f.entities.items())
            groups.setdefault(key, []).append(f)
        formats = self.EEG_FORMATS if kind == "eeg" else self.MEG_FORMATS
        shared = {}
        for f in self.files(folder):
            if f.suffix in self.SHARED:
                shared.setdefault(f.suffix, f.path)
            if kind == "meg" and f.entities.get("acq") == "calibration" and f.suffix == "meg.dat":
                shared.setdefault("calibration_meg.dat", f.path)
            if kind == "meg" and f.entities.get("acq") == "crosstalk" and f.suffix == "meg.fif":
                shared.setdefault("crosstalk_meg.fif", f.path)
        for key, group in groups.items():
            suffixes = {f.suffix for f in group}
            datatype = next((dt for s, dt in formats if s in suffixes), None)
            first = group[0]
            if datatype is None or (kind == "meg" and "task" not in first.entities):
                continue
            first.entities.setdefault("task", "unknown")
            meta = self.inherited(sidecars, first.stem, kind + ".json")
            files = {}
            for f in group:
                if f.suffix == kind + ".json":
                    meta.update(_read_json(f.path))
                    if kind == "meg":
                        continue
                files[f.suffix] = f.path
            for name, path in shared.items():
                files.setdefault(name, path)
            meta.update(first.meta())
            self.add(datatype, key, files, meta, first.tags(), [first.entities["task"].lower()])


def walk(root):
    root = os.path.abspath(root)
    bids = {"participants": [], "participants_json": None, "datasets": []}
    for name in ("participants.tsv", "participant_data.tsv"):
        path = os.path.join(root, name)
        if _exists(path):
            with open(path, encoding="utf-8") as f:
                bids["participants"] = parse_participants(f.read())
    path = os.path.join(root, "participants.json")
    if _exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                columns = escape_dot(json.load(f))
            if isinstance(columns, dict):
                columns.pop("participant_id", None)
                bids["participants_json"] = columns
        except (OSError, ValueError):
            pass  # an unreadable participants.json is ignored; the table still goes up
    bids["datasets"] = Walker(root).walk()
    return bids
