"""Run a brainlife datatype's validator on this computer (in Docker) before its object is uploaded.

The validator repository is cloned from GitHub into a cache; its ``main`` script is read (never
executed) to find the container image and command, which then run with no network on a copy of
the object's files. Staging is under the cache in $HOME, not the system temp folder: Colima
(macOS) mounts only $HOME into its VM.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile

DEFAULT_CACHE = os.path.join(os.path.expanduser("~"), ".cache", "brainlife", "aimport", "validators")
SKIP_MAIN = "validator main is not a single singularity exec"
# docker's messages when it cannot get the image (offline, private or missing); docker run exits 125
PULL_FAILED = re.compile(r"Unable to find image|pull access denied|manifest unknown")
_PLAIN_REPO = re.compile(r"[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*", re.ASCII)
_PLAIN_BRANCH = re.compile(r"[A-Za-z0-9][\w./-]*", re.ASCII)
_PLAIN_IMAGE = re.compile(r"[A-Za-z0-9][\w./:@-]*", re.ASCII)
_SHELL = re.compile(r"[;&|<>$`'\"\\(){}*?]")


def run_command(cmd):
    """-> (exit code, stdout, stderr). OSError when the program cannot be started."""
    p = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def parse_main(text):
    """The single ``singularity exec [-e] docker://<image> <command>`` of a main script, as
    (image, command words), or None."""
    lines = [l.strip() for l in str(text).split("\n")]
    lines = [l for l in lines if l and not l.startswith("#") and not re.fullmatch(r"set\s+-\w+", l)]
    if len(lines) != 1:
        return None
    m = re.fullmatch(r"singularity\s+exec\s+(?:-e\s+)?docker://(\S+)\s+(\S.*)", lines[0])
    if not m:
        return None
    image, command = m.group(1), m.group(2).strip()
    # the command goes to docker as plain words: no shell syntax, nothing option-like
    if _SHELL.search(command) or command.startswith("-") or not _PLAIN_IMAGE.fullmatch(image):
        return None
    return image, command.split()


def _tail(text, n):
    return "\n".join([l for l in text.split("\n") if l.strip()][-n:])


def fetch_validator(datatype, cache_dir, runner):
    """Clone (or update) the validator repository in the cache; returns its folder."""
    repo = datatype["validator"]
    branch = datatype.get("validator_branch") or ""
    folder = os.path.join(cache_dir, re.sub(r"[^\w.@-]", "_", "%s@%s" % (repo, branch or "default"), flags=re.ASCII))
    if os.path.isdir(os.path.join(folder, ".git")):
        code, _out, err = runner(["git", "-C", folder, "fetch", "--depth", "1", "origin", branch or "HEAD"])
        if code == 0:
            code, _out, err = runner(["git", "-C", folder, "reset", "--hard", "FETCH_HEAD"])
        if code != 0:
            raise RuntimeError("git update failed: " + _tail(err, 5))
        return folder
    os.makedirs(cache_dir, exist_ok=True)
    cmd = ["git", "clone", "--depth", "1"] + (["--branch", branch] if branch else [])
    code, _out, err = runner(cmd + ["https://github.com/" + repo, folder])
    if code != 0:
        shutil.rmtree(folder, ignore_errors=True)
        raise RuntimeError("git clone failed: " + _tail(err, 5))
    return folder


def _stage(files, input_dir):
    """Copies (symlinks followed) of the object's files, under their brainlife names."""
    for name, full in files.items():
        dest = os.path.abspath(os.path.join(input_dir, name))
        if not dest.startswith(input_dir + os.sep):
            raise ValueError("file name outside the input folder: " + name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.isdir(full):
            shutil.copytree(full, dest, symlinks=False)
        else:
            shutil.copyfile(full, dest)


def validate_dataset(item, datatype, runner=run_command, cache_dir=DEFAULT_CACHE):
    """-> {"ok": bool, "errors": [...], "warnings": [...], "skipped": reason (only when skipped)}.
    A validator that cannot be run is skipped (the object still goes up, with a warning); one
    that runs and reports errors, crashes or writes no product.json keeps the object out."""
    def skip(reason):
        return {"ok": True, "skipped": reason, "errors": [], "warnings": []}

    if not datatype or not datatype.get("validator"):
        return skip("datatype has no validator")
    # values that go to git as arguments must not look like options or paths
    if not _PLAIN_REPO.fullmatch(datatype["validator"]):
        return skip("validator repo name is not a plain org/repo")
    if datatype.get("validator_branch") and not _PLAIN_BRANCH.fullmatch(datatype["validator_branch"]):
        return skip("validator branch name is not plain")
    for f in datatype.get("files") or []:
        if not f.get("filename") and not f.get("dirname"):
            return skip("datatype file %s has no filename" % f.get("id"))

    try:
        clone = fetch_validator(datatype, cache_dir, runner)
    except (RuntimeError, OSError) as err:
        return skip("validator could not be fetched: %s" % err)
    try:
        with open(os.path.join(clone, "main"), encoding="utf-8") as f:
            main = f.read()
    except OSError:
        return skip("validator has no main script")
    parsed = parse_main(main)
    if not parsed:
        return skip(SKIP_MAIN)
    image, command = parsed

    os.makedirs(cache_dir, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="tmp-", dir=cache_dir)
    try:
        work = os.path.join(tmp, "validator")
        input_dir = os.path.join(tmp, "input")
        shutil.copytree(clone, work, ignore=shutil.ignore_patterns(".git"))
        os.makedirs(input_dir)
        product_path = os.path.join(work, "product.json")
        if os.path.exists(product_path):
            os.remove(product_path)  # never trust one from the repository
        config = {f["id"]: "/input/" + (f.get("filename") or f.get("dirname")) for f in datatype.get("files") or []}
        d = item.get("dataset") or {}
        config["_inputs"] = [{"datatype": datatype.get("_id") or datatype.get("name"), "meta": d.get("meta") or {},
                              "datatype_tags": d.get("datatype_tags") or []}]
        with open(os.path.join(work, "config.json"), "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        _stage(item.get("files") or {}, input_dir)

        cmd = ["docker", "run", "--rm", "--platform", "linux/amd64", "--network", "none",
               "-v", work + ":/validator", "-v", input_dir + ":/input:ro", "-w", "/validator", image] + command
        try:
            code, _out, err = runner(cmd)
        except OSError as e:
            return skip("docker could not be run: %s" % e)

        product = None
        if os.path.exists(product_path):
            try:
                with open(product_path, encoding="utf-8") as f:
                    product = json.load(f)
            except (OSError, ValueError):
                return {"ok": False, "errors": ["validator wrote an unreadable product.json"], "warnings": []}
        if product is None and code == 125 and PULL_FAILED.search(err):
            return skip("validator image could not be pulled: " + _tail(err, 2))
        if product is None:
            why = "validator wrote no product.json" if code == 0 else "validator crashed: " + _tail(err, 5)
            return {"ok": False, "errors": [why], "warnings": []}
        product = product if isinstance(product, dict) else {}
        errors = [str(e) for e in _as_list(product.get("errors"))]
        warnings = [str(w) for w in _as_list(product.get("warnings"))]
        return {"ok": not errors, "errors": errors, "warnings": warnings}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]
