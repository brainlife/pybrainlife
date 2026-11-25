"""Plain-text rendering of the engine's plan (GET /plan) and result (GET /status); no colors."""

import re

MAX_LINE = 160
MAX_ISSUES = 20
ENTITY_ORDER = ("task", "acq", "ce", "rec", "dir", "run", "echo", "part")


def clip(line, limit=MAX_LINE):
    line = re.sub(r"[\r\n]+", " ", str(line))
    return line[: limit - 3] + "..." if len(line) > limit else line


def _set(value):
    return value is not None and value != ""


def bids_name(entry):
    """The BIDS file stem of a plan entry, entities in schema order."""
    parts = ["sub-%s" % entry.get("subject")]
    if entry.get("session"):
        parts.append("ses-%s" % entry["session"])
    entities = entry.get("entities") or {}
    for key in ENTITY_ORDER:
        if _set(entities.get(key)):
            parts.append("%s-%s" % (key, entities[key]))
    parts.append(entry.get("suffix") or "unknown")
    return "_".join(parts)


def _status(entry):
    if entry.get("exclude"):
        return "excluded: " + (entry.get("reason") or entry.get("status") or "excluded")
    return entry.get("status") or "unknown"


def _deface(entry):
    if entry.get("deface_opt_out"):
        return "opted out"
    return "yes" if entry.get("deface") else "no"


def _columns(rows):
    widths = {}
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths.get(i, 0), len(cell))
    return ["  ".join(c if i == len(r) - 1 else c.ljust(widths[i]) for i, c in enumerate(r)) for r in rows]


def render_plan(plan, target=None, deface=None):
    target = target or plan.get("target") or "bids"
    with_bl = target == "datatypes"
    header = ["#", "BIDS name"] + (["brainlife datatype"] if with_bl else []) + ["deface", "status", "source"]
    entries = plan.get("entries") or []
    rows = [header]
    for i, e in enumerate(entries):
        row = [str(i + 1), ((e.get("datatype") + "/") if e.get("datatype") else "") + bids_name(e)]
        if with_bl:
            row.append(e.get("brainlife_datatype") or "-")
        row += [_deface(e), _status(e), "%s %.2f" % (e.get("source") or "none", float(e.get("confidence") or 0))]
        rows.append(row)
    lines = [clip(l) for l in _columns(rows)]
    out = [lines[0]]
    for i, e in enumerate(entries):
        out.append(lines[i + 1])
        if e.get("agent_note"):
            out.append(clip("      note: " + e["agent_note"]))
    out.append("")
    out.append("Dataset name: " + (plan.get("dataset_name") or "-"))
    # the method sent with the approval (--deface), not the engine's default
    out.append("Deface method: " + (deface or plan.get("deface_method") or "pydeface"))
    warnings = plan.get("warnings") or []
    if warnings:
        out.append("")
        out += [clip("! %s" % w) for w in warnings]
    ancillary = plan.get("ancillary") or []
    if ancillary:
        out.append("")
        out.append("Ancillary files:")
        arows = [[str(a.get("path")), str(a.get("action")), ", ".join(a.get("flags") or [])] for a in ancillary]
        out += [clip("  " + l.rstrip()) for l in _columns(arows)]
    return "\n".join(out) + "\n"


def render_result(status):
    out = ["Stage: %s" % status.get("stage") + (" (%s)" % status["message"] if status.get("message") else "")]
    if status.get("output_dir"):
        out.append("Output folder: " + status["output_dir"])
    v = status.get("validation")
    if v:
        errors = v.get("errors") or []
        warnings = v.get("warnings") or []
        ec = v["error_count"] if v.get("error_count") is not None else len(errors)
        wc = v["warning_count"] if v.get("warning_count") is not None else len(warnings)
        out.append("Validation: %s error(s), %s warning(s)" % (ec, wc))
        issues = [("error", i) for i in errors] + [("warning", i) for i in warnings]
        for sev, i in issues[:MAX_ISSUES]:
            files = ", ".join((i.get("files") or [])[:3])
            out.append(clip("  %s %s: %s%s" % (sev, i.get("code") or "", i.get("message") or "",
                                               " [%s]" % files if files else "")))
        if len(issues) > MAX_ISSUES:
            out.append("  ... and %d more" % (len(issues) - MAX_ISSUES))
    return "\n".join(out) + "\n"
