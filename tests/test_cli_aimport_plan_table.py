"""bl aimport: the plan and result as shown in the terminal."""

from brainlife.cli.aimport.plan_table import bids_name, render_plan, render_result


def plan():
    return {
        "dataset_name": "Pilot study", "deface_method": "pydeface",
        "warnings": ["Series 7 could not be classified"],
        "entries": [
            {"id": "a", "subject": "01", "session": "1", "datatype": "anat", "suffix": "T1w", "entities": {},
             "brainlife_datatype": "neuro/anat/t1w", "source": "agent", "confidence": 0.9, "deface": True,
             "deface_opt_out": True, "status": "ok"},
            {"id": "b", "subject": "01", "session": "1", "datatype": "func", "suffix": "bold",
             "entities": {"run": "2", "task": "rest"}, "brainlife_datatype": "neuro/func/task", "source": "heuristic",
             "confidence": 0.75, "deface": False, "status": "ok", "agent_note": "task-rest rather than task-resting"},
            {"id": "c", "subject": "01", "session": "1", "datatype": "fmap", "suffix": "magnitude1", "entities": {},
             "brainlife_datatype": None, "source": "heuristic", "confidence": 0.5, "exclude": True,
             "reason": "magnitude not needed", "status": "excluded_by_default"},
            {"id": "d", "subject": "01", "session": None, "datatype": None, "suffix": None, "entities": {},
             "source": None, "confidence": None, "status": "unknown"},
        ],
        "ancillary": [{"path": "participants.tsv", "action": "edit", "flags": ["free text column"]},
                      {"path": "README", "action": "keep", "flags": []}],
    }


def test_bids_name_puts_entities_in_schema_order_and_skips_empty_ones():
    assert bids_name({"subject": "01", "session": "2", "entities": {"run": 1, "task": "rest", "acq": ""},
                      "suffix": "bold"}) == "sub-01_ses-2_task-rest_run-1_bold"
    assert bids_name({"subject": "03", "entities": None, "suffix": None}) == "sub-03_unknown"


def test_plan_rows_show_name_deface_status_and_source():
    text = render_plan(plan(), target="bids")
    assert "anat/sub-01_ses-1_T1w" in text
    assert "func/sub-01_ses-1_task-rest_run-2_bold" in text
    assert "opted out" in text and "agent 0.90" in text
    assert "excluded: magnitude not needed" in text
    assert "sub-01_unknown" in text and "none 0.00" in text
    assert "note: task-rest rather than task-resting" in text
    assert "! Series 7 could not be classified" in text
    assert "participants.tsv  edit  free text column" in text
    assert "Dataset name: Pilot study" in text
    assert "neuro/anat/t1w" not in text  # the datatype column is for --target datatypes


def test_datatypes_target_adds_the_brainlife_column():
    text = render_plan(plan(), target="datatypes")
    assert "brainlife datatype" in text and "neuro/func/task" in text
    row = next(l for l in text.splitlines() if "magnitude1" in l)
    assert " - " in row


def test_the_chosen_deface_method_is_shown_not_the_engine_default():
    assert "Deface method: quickshear" in render_plan(plan(), deface="quickshear")
    p = dict(plan(), deface_method=None, dataset_name=None)
    text = render_plan(p)
    assert "Deface method: pydeface" in text and "Dataset name: -" in text and "None" not in text


def test_every_line_fits_160_columns():
    p = plan()
    p["warnings"] = ["w" * 500]
    p["entries"][0]["agent_note"] = "line one\nline two " + "n" * 300
    for line in render_plan(p, target="datatypes").splitlines():
        assert len(line) <= 160
    assert "line one line two" in render_plan(p)


def test_result_lists_at_most_20_issues():
    errors = [{"code": "E%d" % i, "message": "bad", "files": ["a.json", "b.json", "c.json", "d.json"]} for i in range(23)]
    text = render_result({"stage": "invalid", "message": "23 validation error(s)", "output_dir": "/work/output/bids",
                          "validation": {"error_count": 23, "warning_count": 1, "errors": errors,
                                         "warnings": [{"code": "W1", "message": "meh"}]}})
    assert text.startswith("Stage: invalid (23 validation error(s))")
    assert "Output folder: /work/output/bids" in text
    assert "Validation: 23 error(s), 1 warning(s)" in text
    assert len([l for l in text.splitlines() if l.startswith("  error E")]) == 20
    assert "[a.json, b.json, c.json]" in text
    assert "... and 4 more" in text


def test_result_counts_issues_when_the_engine_gives_no_counts():
    text = render_result({"stage": "validated", "validation": {"errors": [], "warnings": [{"code": "W"}]}})
    assert "Validation: 0 error(s), 1 warning(s)" in text
