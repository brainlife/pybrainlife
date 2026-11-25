"""bl aimport: from the engine's output folder to brainlife objects and project files."""

import json
import os

import pytest

from brainlife.cli.aimport.bids_walker import parse_participants, walk
from brainlife.cli.aimport.objects import (RefusedError, apply_plan, keep_channels, micr_datasets, preflight,
                                           project_files)

from .aimport_support import DATATYPES, make_bids, write

BY_NAME = {d["name"]: d for d in DATATYPES}


@pytest.fixture
def bids(tmp_path):
    return make_bids(str(tmp_path / "bids"))


def by_desc(datasets):
    return {d["dataset"]["desc"]: d for d in datasets}


# --- the walker ---------------------------------------------------------------------------------

def test_walker_finds_each_image_with_its_datatype_files_and_meta(bids):
    w = walk(bids)
    objs = by_desc(w["datasets"])
    assert sorted(objs) == ["sub-01_T1w.nii.gz", "sub-01_dwi.nii.gz", "sub-01_task-rest_run-1_bold.nii.gz",
                            "sub-02_ses-1_T1w.nii.gz", "sub-02_ses-1_T2w.nii.gz"]
    t1 = objs["sub-01_T1w.nii.gz"]
    assert t1["dataset"]["datatype"] == "neuro/anat/t1w"
    assert t1["dataset"]["meta"] == {"EchoTime": 0.003, "subject": "01"}
    assert t1["files"] == {"t1.nii.gz": os.path.join(bids, "sub-01", "anat", "sub-01_T1w.nii.gz")}
    bold = objs["sub-01_task-rest_run-1_bold.nii.gz"]["dataset"]
    assert bold["datatype"] == "neuro/func/task" and bold["datatype_tags"] == ["rest"]
    assert bold["tags"] == ["task-rest", "run-1"]
    # the root-level task-rest_bold.json is inherited
    assert bold["meta"] == {"RepetitionTime": 2, "TaskName": "rest", "subject": "01", "task": "rest", "run": "1"}
    assert set(objs["sub-01_task-rest_run-1_bold.nii.gz"]["files"]) == {"bold.nii.gz", "events.tsv"}
    assert set(objs["sub-01_dwi.nii.gz"]["files"]) == {"dwi.nii.gz", "dwi.bvecs", "dwi.bvals"}
    t2 = objs["sub-02_ses-1_T2w.nii.gz"]["dataset"]
    assert t2["datatype"] == "neuro/anat/t2w" and t2["meta"] == {"subject": "02", "session": "1"}


def test_walker_reads_the_participants_table(bids):
    w = walk(bids)
    assert w["participants"] == [{"subject": "01", "age": "30"}, {"subject": "02", "age": "40"}]
    assert w["participants_json"] == {"age": {"Description": "age in years"}}


def test_participants_header_dots_are_escaped_and_the_id_column_found():
    rows = parse_participants("age\tparticipant_id\tscore.v1\r\n30\tsub-07\t5\r\n")
    assert rows == [{"subject": "07", "age": "30", "score-v1": "5"}]


def test_sidecar_keys_with_dots_are_escaped(tmp_path):
    root = str(tmp_path)
    write(os.path.join(root, "sub-01", "anat", "sub-01_T1w.nii.gz"), b"x")
    write(os.path.join(root, "sub-01", "anat", "sub-01_T1w.json"), '{"Scan.Options": {"a.b": 1}}')
    meta = walk(root)["datasets"][0]["dataset"]["meta"]
    assert meta == {"Scan-Options": {"a-b": 1}, "subject": "01"}


def test_pepolar_field_maps_sharing_intended_for_are_one_object(tmp_path):
    root = str(tmp_path)
    f = os.path.join(root, "sub-01", "fmap")
    intended = json.dumps({"IntendedFor": ["func/sub-01_task-rest_bold.nii.gz"], "TotalReadoutTime": 0.05})
    for d, run in (("AP", "1"), ("PA", "2")):
        write(os.path.join(f, "sub-01_dir-%s_run-%s_epi.nii.gz" % (d, run)), b"x")
        write(os.path.join(f, "sub-01_dir-%s_run-%s_epi.json" % (d, run)), intended)
    objs = walk(root)["datasets"]
    assert len(objs) == 1
    o = objs[0]
    assert o["dataset"]["datatype"] == "neuro/fmap" and o["dataset"]["datatype_tags"] == ["pepolar"]
    assert set(o["files"]) == {"epi1.nii.gz", "epi1.json", "epi2.nii.gz", "epi2.json"}
    assert "dir" not in o["dataset"]["meta"] and o["dataset"]["meta"]["TotalReadoutTime"] == 0.05


def test_phasediff_field_map_takes_its_magnitudes(tmp_path):
    root = str(tmp_path)
    f = os.path.join(root, "sub-01", "fmap")
    for n in ("phasediff.nii.gz", "phasediff.json", "magnitude1.nii.gz", "magnitude2.nii.gz"):
        write(os.path.join(f, "sub-01_" + n), "{}" if n.endswith("json") else b"x")
    o = walk(root)["datasets"][0]
    assert o["dataset"]["datatype_tags"] == ["phasediff"]
    assert set(o["files"]) == {"phasediff.nii.gz", "phasediff.json", "magnitude1.nii.gz", "magnitude2.nii.gz"}


STEM = "sub-01/eeg/sub-01_task-rest_"
TSV = "name\ttype\tunits\tstatus\tstatus_description\nFp1\tEEG\tV\tbad\tflat\nCz\tEEG\tV\tgood\tn/a\n"


def eeg_tree(root):
    write(os.path.join(root, "dataset_description.json"), '{"Name": "x"}')
    for n in ("eeg.vhdr", "eeg.eeg", "eeg.vmrk", "eeg.json", "channels.tsv", "channels.json", "events.tsv"):
        write(os.path.join(root, STEM + n), TSV if n == "channels.tsv" else "{}" if n.endswith(".json") else n)
    write(os.path.join(root, "sub-01", "eeg", "sub-01_electrodes.tsv"), "name\tx\n")
    return root


def test_an_eeg_recording_keeps_channels_and_shared_files(tmp_path):
    root = eeg_tree(str(tmp_path))
    objs = walk(root)["datasets"]
    assert len(objs) == 1
    eeg = objs[0]
    assert eeg["dataset"]["datatype"] == "neuro/eeg/brainvision" and eeg["dataset"]["datatype_tags"] == ["rest"]
    assert eeg["files"]["channels.tsv"] == os.path.join(root, STEM + "channels.tsv")
    assert eeg["files"]["electrodes.tsv"].endswith("sub-01_electrodes.tsv")
    assert {"eeg.vhdr", "eeg.eeg", "eeg.vmrk", "channels.json", "events.tsv"} <= set(eeg["files"])


# --- the plan's brainlife mapping ---------------------------------------------------------------

T1_ENTRY = {"id": "e1", "subject": "01", "session": None, "datatype": "anat", "suffix": "T1w", "entities": {},
            "brainlife_datatype": "neuro/anat/t2w", "brainlife_tags": ["mine"]}


def test_apply_plan_sets_the_reviewed_datatype_and_tags(bids):
    w = walk(bids)
    manifest = {"e1": ["sub-01/anat/sub-01_T1w.nii.gz", "sub-01/anat/sub-01_T1w.json"]}
    datasets, warnings, notes = apply_plan(w, {"entries": [T1_ENTRY]}, manifest, BY_NAME, bids)
    assert warnings == [] and notes == [] and len(datasets) == 5
    objs = by_desc(datasets)
    assert objs["sub-01_T1w.nii.gz"]["dataset"]["datatype"] == "neuro/anat/t2w"
    assert objs["sub-01_T1w.nii.gz"]["dataset"]["datatype_tags"] == ["mine"]
    assert objs["sub-02_ses-1_T1w.nii.gz"]["dataset"]["datatype"] == "neuro/anat/t1w"


def test_a_draft_datatype_keeps_the_object_out_with_a_warning(bids):
    entry = dict(T1_ENTRY, brainlife_datatype="neuro/anat/draft")
    datasets, warnings, _ = apply_plan(walk(bids), {"entries": [entry]}, {"e1": ["sub-01/anat/sub-01_T1w.nii.gz"]},
                                       BY_NAME, bids)
    assert "sub-01_T1w.nii.gz" not in by_desc(datasets)
    assert warnings == ["neuro/anat/draft is not a registered brainlife datatype (draft): sub-01_T1w goes to project files only"]
    assert "sub-01/anat/sub-01_T1w.nii.gz" in project_files(bids, datasets)


def test_an_entry_without_a_brainlife_datatype_leaves_the_walker_choice(bids):
    entry = dict(T1_ENTRY, brainlife_datatype=None)
    datasets, _, _ = apply_plan(walk(bids), {"entries": [entry]}, {"e1": ["sub-01/anat/sub-01_T1w.nii.gz"]}, BY_NAME, bids)
    assert by_desc(datasets)["sub-01_T1w.nii.gz"]["dataset"]["datatype"] == "neuro/anat/t1w"


EEG_ENTRY = {"id": "e1", "subject": "01", "session": None, "datatype": "eeg", "suffix": "eeg",
             "entities": {"task": "rest"}, "brainlife_datatype": "neuro/eeg/brainvision", "brainlife_tags": ["rest"]}


def test_ephys_objects_map_channels_tsv_and_carry_channels_json_as_an_extra_file(tmp_path):
    root = eeg_tree(str(tmp_path))
    manifest = {"e1": [STEM + n for n in ("eeg.vhdr", "eeg.eeg", "eeg.vmrk", "channels.tsv", "channels.json")]}
    datasets, _, notes = apply_plan(walk(root), {"entries": [EEG_ENTRY]}, manifest, BY_NAME, root)
    assert datasets[0]["files"]["channels.tsv"] == os.path.join(root, STEM + "channels.tsv")
    assert notes == ["channels.json kept with sub-01_task-rest_eeg as an extra file "
                     "(neuro/eeg/brainvision has no channels.json file)"]
    assert not any("channels" in f for f in project_files(root, datasets))


def test_keep_channels_adds_only_what_the_manifest_lists(tmp_path):
    root = eeg_tree(str(tmp_path))
    item = {"dataset": {}, "files": {}}
    dt = {"name": "neuro/meg/fif", "files": [{"id": "channels", "filename": "channels.tsv"}]}
    assert keep_channels(item, EEG_ENTRY, {"e1": [STEM + "channels.tsv"]}, dt, root) == []
    assert list(item["files"]) == ["channels.tsv"]
    item = {"dataset": {}, "files": {}}
    notes = keep_channels(item, EEG_ENTRY, {"e1": [STEM + "channels.tsv", STEM + "channels.json"]},
                          {"name": "neuro/ieeg/edf", "files": []}, root)
    assert len(notes) == 2 and set(item["files"]) == {"channels.tsv", "channels.json"}


# --- micr ---------------------------------------------------------------------------------------

ZARR = "sub-01/micr/sub-01_sample-01_OCT.ome.zarr"
MICR_PLAN = {"entries": [
    {"id": "m1", "modality": "micr", "subject": "01", "session": None, "datatype": "micr", "suffix": "OCT",
     "entities": {"sample": "01"}, "brainlife_datatype": "neuro/ome-zarr", "brainlife_tags": ["OCT"]},
    {"id": "m2", "modality": "micr", "subject": "01", "exclude": True, "brainlife_datatype": "neuro/ome-zarr"},
]}


def micr_tree(root):
    write(os.path.join(root, ZARR, "zarr.json"), "{}")
    write(os.path.join(root, ZARR, "0", "zarr.json"), "{}")
    write(os.path.join(root, "sub-01", "micr", "sub-01_sample-01_OCT.json"), "{}")
    write(os.path.join(root, "dataset_description.json"), "{}")
    return root


def test_each_written_store_of_a_micr_entry_is_one_object(tmp_path):
    root = micr_tree(str(tmp_path))
    datasets, warnings, held = micr_datasets(root, MICR_PLAN, {"m1": [ZARR], "m2": ["x.ome.zarr"]}, BY_NAME)
    assert warnings == [] and held == []
    assert datasets == [{"dataset": {"datatype": "neuro/ome-zarr", "desc": "sub-01_sample-01_OCT.ome.zarr",
                                     "datatype_tags": ["OCT"], "tags": [], "meta": {"subject": "01", "sample": "01"}},
                         "files": {"data.ome.zarr": os.path.join(root, ZARR)}}]
    assert project_files(root, datasets) == ["dataset_description.json", "sub-01/micr/sub-01_sample-01_OCT.json"]


def test_a_store_without_a_registered_datatype_is_held_back(tmp_path):
    root = micr_tree(str(tmp_path))
    datasets, warnings, held = micr_datasets(root, MICR_PLAN, {"m1": [ZARR]}, {})
    assert datasets == [] and "not a registered brainlife datatype" in warnings[0]
    assert project_files(root, [], held) == ["dataset_description.json", "sub-01/micr/sub-01_sample-01_OCT.json"]


# --- safety and project files -------------------------------------------------------------------

def test_preflight_accepts_a_plain_output(bids):
    preflight(bids)


@pytest.mark.parametrize("plant,match", [
    (lambda r: os.symlink("/etc/hosts", os.path.join(r, "sub-01", "anat", "link.nii.gz")), "symbolic link"),
    (lambda r: os.symlink(os.path.join(r, "sub-02"), os.path.join(r, "sub-03")), "sub-03: it is a symbolic link"),
    (lambda r: write(os.path.join(r, "sub-01", "p.aimport-key.json"), "{}"), "key files never leave"),
    (lambda r: os.makedirs(os.path.join(r, "sub-01", "sourcedata")), "sourcedata never leaves"),
    (lambda r: os.mkfifo(os.path.join(r, "pipe")), "not a regular file"),
])
def test_preflight_refuses(bids, plant, match):
    plant(bids)
    with pytest.raises(RefusedError, match=match):
        preflight(bids)


def test_preflight_refuses_a_missing_output(tmp_path):
    with pytest.raises(RefusedError, match="missing"):
        preflight(str(tmp_path / "nothing"))


def test_project_files_are_the_metadata_not_object_files_or_participants(bids):
    files = project_files(bids, walk(bids)["datasets"])
    assert files == ["CHANGES", "README", "dataset_description.json", "phenotype/moca.tsv",
                     "sub-01/anat/sub-01_T1w.json", "sub-02/ses-1/sub-02_ses-1_scans.tsv", "task-rest_bold.json"]


def test_project_files_refuse_sourcedata_and_keys(bids):
    write(os.path.join(bids, "sourcedata", "x"), "secret")
    with pytest.raises(RefusedError, match="sourcedata"):
        project_files(bids, [])
