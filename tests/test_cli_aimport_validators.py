"""bl aimport: running a datatype's validator on this computer before its object is uploaded."""

import json
import os

import pytest

from brainlife.cli.aimport.validators import SKIP_MAIN, parse_main, validate_dataset

from .aimport_support import write

MAIN = "#!/bin/bash\n#PBS -l nodes=1:ppn=1\n\nset -e\n\nsingularity exec -e docker://brainlife/dipy:1.1.1 ./validate.py --strict\n"
DATATYPE = {"_id": "dt1", "name": "neuro/anat/t1w", "validator": "brainlife/validator-neuro-anat",
            "validator_branch": "1.0", "files": [{"id": "t1", "filename": "t1.nii.gz"}, {"id": "dir", "dirname": "stuff"}]}


class Runner:
    """Stands in for git and docker: git clone writes `main`; docker records what it was given
    and writes product.json."""

    def __init__(self, main=MAIN, product=None, code=0, stderr="", docker_error=None):
        self.main, self.product, self.code, self.stderr, self.docker_error = main, product, code, stderr, docker_error
        self.calls = []
        self.seen = {}

    def __call__(self, cmd):
        self.calls.append(cmd)
        if cmd[0] == "git":
            if cmd[1] == "clone":
                write(os.path.join(cmd[-1], ".git", "HEAD"), "ref")
                write(os.path.join(cmd[-1], "main"), self.main)
            return 0, "", ""
        if self.docker_error:
            raise self.docker_error
        work = cmd[cmd.index("-v") + 1].split(":")[0]
        inp = cmd[len(cmd) - 1 - cmd[::-1].index("-v") + 1].split(":")[0]
        with open(os.path.join(work, "config.json")) as f:
            self.seen["config"] = json.load(f)
        self.seen["inputs"] = sorted(os.listdir(inp))
        self.seen["t1_is_copy"] = not os.path.islink(os.path.join(inp, "t1.nii.gz"))
        self.seen["product_before"] = os.path.exists(os.path.join(work, "product.json"))
        if self.product is not None:
            write(os.path.join(work, "product.json"), json.dumps(self.product))
        return self.code, "", self.stderr


@pytest.fixture
def item(tmp_path):
    src = tmp_path / "src"
    write(str(src / "t1.nii.gz"), "x")
    write(str(src / "stuff" / "a.txt"), "y")
    os.symlink(str(src / "t1.nii.gz"), str(tmp_path / "t1-link.nii.gz"))
    return {"dataset": {"datatype": "neuro/anat/t1w", "datatype_tags": ["t"], "meta": {"subject": "01"}},
            "files": {"t1.nii.gz": str(tmp_path / "t1-link.nii.gz"), "stuff": str(src / "stuff")}}


@pytest.fixture
def cache(tmp_path):
    return str(tmp_path / "cache")


def test_parse_main_reads_image_and_command_of_a_single_singularity_exec():
    assert parse_main(MAIN) == ("brainlife/dipy:1.1.1", ["./validate.py", "--strict"])
    assert parse_main("singularity exec docker://a/b:1 ./run.py") == ("a/b:1", ["./run.py"])


@pytest.mark.parametrize("text", [
    "#!/bin/bash\npython run.py\n",
    "singularity exec docker://a/b:1 ./run.py\nrm -rf x\n",
    "singularity exec docker://a/b:1 ./run.py; rm x\n",
    "singularity exec docker://a/b:1 ./run.py $(id)\n",
    "singularity exec docker://-v/:/host ./run.py\n",
    "singularity exec docker://a/b:1 --privileged\n",
])
def test_parse_main_refuses_anything_else(text):
    assert parse_main(text) is None


def test_the_validator_runs_offline_on_copies_with_a_written_config(item, cache):
    r = Runner(product={"errors": [], "warnings": ["w"]})
    assert validate_dataset(item, DATATYPE, runner=r, cache_dir=cache) == {"ok": True, "errors": [], "warnings": ["w"]}
    clone, docker = r.calls
    assert clone[:6] == ["git", "clone", "--depth", "1", "--branch", "1.0"]
    assert "https://github.com/brainlife/validator-neuro-anat" in clone
    assert docker[docker.index("--network") + 1] == "none"
    assert "linux/amd64" in docker and docker[-3:] == ["brainlife/dipy:1.1.1", "./validate.py", "--strict"]
    assert any(a.endswith(":/input:ro") for a in docker)
    assert r.seen["config"]["t1"] == "/input/t1.nii.gz" and r.seen["config"]["dir"] == "/input/stuff"
    assert r.seen["config"]["_inputs"] == [{"datatype": "dt1", "meta": {"subject": "01"}, "datatype_tags": ["t"]}]
    assert r.seen["inputs"] == ["stuff", "t1.nii.gz"] and r.seen["t1_is_copy"]
    # staged under the cache in $HOME (Colima), and cleaned up
    assert docker[docker.index("-v") + 1].startswith(os.path.join(cache, "tmp-"))
    assert [n for n in os.listdir(cache) if n.startswith("tmp-")] == []


def test_errors_in_product_json_keep_the_object_out(item, cache):
    r = validate_dataset(item, DATATYPE, runner=Runner(product={"errors": ["bad header"]}), cache_dir=cache)
    assert r == {"ok": False, "errors": ["bad header"], "warnings": []}


def test_a_crash_reports_the_last_five_stderr_lines(item, cache):
    r = validate_dataset(item, DATATYPE, runner=Runner(code=1, stderr="\n".join("1234567")), cache_dir=cache)
    assert r["ok"] is False and r["errors"] == ["validator crashed: 3\n4\n5\n6\n7"]


def test_no_product_json_after_a_clean_exit_is_not_ok(item, cache):
    r = validate_dataset(item, DATATYPE, runner=Runner(), cache_dir=cache)
    assert r["ok"] is False and r["errors"] == ["validator wrote no product.json"]


def test_a_product_json_from_the_repository_is_never_trusted(item, cache):
    clone = os.path.join(cache, "brainlife_validator-neuro-anat@1.0")
    write(os.path.join(clone, ".git", "HEAD"), "ref")
    write(os.path.join(clone, "main"), MAIN)
    write(os.path.join(clone, "product.json"), '{"errors": []}')
    r = Runner()
    assert validate_dataset(item, DATATYPE, runner=r, cache_dir=cache)["ok"] is False
    assert r.seen["product_before"] is False


def test_a_cached_clone_is_updated_not_cloned_again(item, cache):
    validate_dataset(item, DATATYPE, runner=Runner(product={}), cache_dir=cache)
    r = Runner(product={})
    validate_dataset(item, DATATYPE, runner=r, cache_dir=cache)
    assert r.calls[0][3:5] == ["fetch", "--depth"] and r.calls[1][3:5] == ["reset", "--hard"]


def test_an_image_that_cannot_be_pulled_skips_the_check(item, cache):
    err = "Unable to find image 'brainlife/dipy:1.1.1' locally\ndocker: pull access denied for brainlife/dipy\n"
    r = validate_dataset(item, DATATYPE, runner=Runner(code=125, stderr=err), cache_dir=cache)
    assert r["ok"] is True and r["skipped"].startswith("validator image could not be pulled:")
    # but a validator that crashes after a pull is not ok
    r = validate_dataset(item, DATATYPE, runner=Runner(code=1, stderr="Unable to find image\nTraceback"), cache_dir=cache)
    assert r["ok"] is False


def test_docker_missing_skips_the_check(item, cache):
    r = validate_dataset(item, DATATYPE, runner=Runner(docker_error=FileNotFoundError("docker")), cache_dir=cache)
    assert r["ok"] is True and r["skipped"].startswith("docker could not be run")


@pytest.mark.parametrize("datatype,reason", [
    ({"name": "x", "validator": "", "files": []}, "datatype has no validator"),
    (dict(DATATYPE, validator="../x"), "validator repo name is not a plain org/repo"),
    (dict(DATATYPE, validator_branch="--upload-pack=x"), "validator branch name is not plain"),
    (dict(DATATYPE, files=[{"id": "zz"}]), "datatype file zz has no filename"),
])
def test_unusable_definitions_are_skipped_without_running_anything(item, cache, datatype, reason):
    r = Runner()
    assert validate_dataset(item, datatype, runner=r, cache_dir=cache)["skipped"] == reason
    assert r.calls == []


def test_a_main_that_is_not_a_single_exec_is_skipped_without_docker(item, cache):
    r = Runner(main="#!/bin/bash\npython run.py\n")
    assert validate_dataset(item, DATATYPE, runner=r, cache_dir=cache)["skipped"] == SKIP_MAIN
    assert all(c[0] == "git" for c in r.calls)


def test_a_failed_clone_skips_and_leaves_no_folder(item, cache):
    def runner(cmd):
        return 128, "", "fatal: repository not found"
    r = validate_dataset(item, DATATYPE, runner=runner, cache_dir=cache)
    assert r["skipped"].startswith("validator could not be fetched: git clone failed")
    assert os.listdir(cache) == []
