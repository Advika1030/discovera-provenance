"""
Layer 2: deterministic checks over the parsed runs, producing one row per
issue in outputs/flags.csv.

No LLM is involved anywhere in this file — every check is a plain rule over
the structured data that parse_logs.py already extracted. Each flag has a
"severity" (high / medium / low) reflecting how confident we are that it
indicates a real problem with the agent's trajectory, not just a judgment
call about the parser being unsure.

Run `python3 src/parse_logs.py` first (or just run this file, which calls it
for you) to make sure outputs/runs.csv etc. are up to date.
"""

import json
from collections import defaultdict

import pandas as pd

from parse_logs import OUTPUTS_DIR, load_all_runs, urls_match

# Tools whose output tables are consumed by *another tool call* in a normal
# trajectory. Final-answer tools (gsea_pipe, ora_pipe, run_deseq2_*) feed the
# report directly and are expected to be "dead ends" from the tool graph's
# point of view, so DEAD_END is restricted to these four (NOTES.md / plan
# item 4).
DEAD_END_TOOLS = {"csv_filter", "csv_select", "csv_join", "csv_aggregate"}


def flag(run, step_index, tool, flag_type, severity, detail):
    return {
        "run": run,
        "step_index": step_index,
        "tool": tool,
        "flag_type": flag_type,
        "severity": severity,
        "detail": detail,
    }


def check_no_tool_calls(run):
    if len(run["steps"]) == 0:
        return [flag(run["run"], None, None, "NO_TOOL_CALLS", "high",
                      "run made zero tool calls")]
    return []


def check_unknown_input_id(run):
    flags = []
    produced = set()
    for step in run["steps"]:
        for input_id in step["input_ids"]:
            if input_id not in produced:
                flags.append(flag(
                    run["run"], step["index"], step["tool"], "UNKNOWN_INPUT_ID", "high",
                    f"referenced id {input_id!r} was never produced by an earlier step",
                ))
        for entry in step["output_entries"]:
            produced.add(entry["id"])
    return flags


def check_tool_error(run):
    flags = []
    for step in run["steps"]:
        if step["error"]:
            err = step["error"]
            flags.append(flag(
                run["run"], step["index"], step["tool"], "TOOL_ERROR", "medium",
                f"{err.get('type')}: {err.get('message')}",
            ))
    return flags


def check_failed_load(run):
    # Specialized, high-severity view of TOOL_ERROR specifically for
    # csv_record: a failed ingestion means the agent never actually got the
    # data it thinks it's analyzing. This deliberately overlaps with
    # TOOL_ERROR (same underlying event, two different lenses) rather than
    # suppressing the generic flag.
    flags = []
    for step in run["steps"]:
        if step["tool"] == "csv_record" and step["error"]:
            err = step["error"]
            flags.append(flag(
                run["run"], step["index"], step["tool"], "FAILED_LOAD", "high",
                f"{err.get('type')}: {err.get('message')}",
            ))
    return flags


def check_unused_upload(run):
    # Only flags files the agent never even *attempted* to load (no
    # matching csv_record call at all, success or fail). A file that was
    # attempted but failed to load is FAILED_LOAD's concern, not this one.
    flags = []
    attempted_urls = [
        step["args"].get("csv_url")
        for step in run["steps"]
        if step["tool"] == "csv_record" and step["args"].get("csv_url")
    ]
    for uf in run["uploaded_files"]:
        url = uf.get("url")
        if not any(urls_match(url, attempted) for attempted in attempted_urls):
            flags.append(flag(
                run["run"], None, "csv_record", "UNUSED_UPLOAD", "high",
                f"uploaded file {uf.get('name')!r} was never passed to csv_record",
            ))
    return flags


def check_repeated_call(run):
    # Exact-duplicate calls: same tool, identical args. Flags every
    # occurrence after the first. csv_read is marked low severity since
    # re-reading a table is mostly harmless; everything else is medium.
    flags = []
    seen = {}  # (tool, normalized_args_json) -> first step_index
    for step in run["steps"]:
        key = (step["tool"], json.dumps(step["args"], sort_keys=True))
        if key in seen:
            severity = "low" if step["tool"] == "csv_read" else "medium"
            flags.append(flag(
                run["run"], step["index"], step["tool"], "REPEATED_CALL", severity,
                f"identical call to step {seen[key]}",
            ))
        else:
            seen[key] = step["index"]
    return flags


def check_same_input_repeat(run):
    # Softer signal: same tool called on the same input table(s), but with
    # different other params (e.g. different gene_sets). Skips pairs that
    # are already exact duplicates (those are REPEATED_CALL's concern).
    flags = []
    seen = {}  # (tool, frozenset(input_ids)) -> first step_index
    for step in run["steps"]:
        if not step["input_ids"]:
            continue
        key = (step["tool"], frozenset(step["input_ids"]))
        exact_key = (step["tool"], json.dumps(step["args"], sort_keys=True))
        if key in seen:
            first_index, first_exact_key = seen[key]
            if exact_key != first_exact_key:
                flags.append(flag(
                    run["run"], step["index"], step["tool"], "SAME_INPUT_REPEAT", "low",
                    f"same tool + same input table(s) as step {first_index}, "
                    f"but with different params",
                ))
        else:
            seen[key] = (step["index"], exact_key)
    return flags


def check_dead_end(run):
    flags = []
    all_later_inputs = defaultdict(set)  # step_index -> ids it consumes
    for step in run["steps"]:
        all_later_inputs[step["index"]] = set(step["input_ids"])

    for step in run["steps"]:
        if step["tool"] not in DEAD_END_TOOLS:
            continue
        for entry in step["output_entries"]:
            if entry["is_plot"]:
                continue
            used_later = any(
                entry["id"] in all_later_inputs[later["index"]]
                for later in run["steps"]
                if later["index"] > step["index"]
            )
            if not used_later:
                flags.append(flag(
                    run["run"], step["index"], step["tool"], "DEAD_END", "low",
                    f"table {entry['id']} produced but never used by a later step",
                ))
    return flags


def check_slow_or_long(runs):
    # Compare each run against others with the same (task_id, mode, model) —
    # with only ~5 runs per group, raw "> 2x median" is too noisy (2 steps vs
    # 1 step would trip it), so require an absolute margin too.
    flags = []
    groups = defaultdict(list)
    for run in runs:
        key = (run["task_id"], run["mode"], run["model"])
        groups[key].append(run)

    for key, group in groups.items():
        if len(group) < 2:
            continue
        steps_median = pd.Series([len(r["steps"]) for r in group]).median()
        elapsed_median = pd.Series([r["elapsed"] for r in group]).median()

        for run in group:
            n_steps = len(run["steps"])
            reasons = []
            if n_steps > 2 * steps_median and n_steps >= steps_median + 5:
                reasons.append(f"n_steps={n_steps} vs group median={steps_median}")
            if run["elapsed"] and run["elapsed"] > 2 * elapsed_median and \
                    run["elapsed"] >= elapsed_median + 120:
                reasons.append(f"elapsed={run['elapsed']}s vs group median={elapsed_median}s")
            if reasons:
                flags.append(flag(
                    run["run"], None, None, "SLOW_OR_LONG", "low",
                    f"group={key}, n={len(group)} runs: " + "; ".join(reasons),
                ))
    return flags


def run_all_checks(runs):
    rows = []
    for run in runs:
        rows += check_no_tool_calls(run)
        rows += check_unknown_input_id(run)
        rows += check_tool_error(run)
        rows += check_failed_load(run)
        rows += check_unused_upload(run)
        rows += check_repeated_call(run)
        rows += check_same_input_repeat(run)
        rows += check_dead_end(run)
    rows += check_slow_or_long(runs)
    return pd.DataFrame(rows)


def print_summary(runs, flags_df):
    run_meta = {r["run"]: r for r in runs}

    print("\n=== Flag counts per model x mode ===")
    meta_df = pd.DataFrame(
        {"run": r["run"], "model": r["model"], "mode": r["mode"]} for r in runs
    )
    merged = flags_df.merge(meta_df, on="run", how="left")
    print(merged.groupby(["model", "mode", "flag_type"]).size().unstack(fill_value=0))

    print("\n=== Top 10 most-flagged runs ===")
    top = flags_df.groupby("run").size().sort_values(ascending=False).head(10)
    for run_id, count in top.items():
        r = run_meta[run_id]
        print(f"  {count:3d} flags  {run_id}  ({r['model']}, task {r['task_id']})")


def main():
    from parse_logs import main as parse_main
    runs = parse_main()

    flags_df = run_all_checks(runs)
    flags_df.to_csv(OUTPUTS_DIR / "flags.csv", index=False)
    print(f"\nWrote {OUTPUTS_DIR / 'flags.csv'} ({len(flags_df)} rows)")

    print_summary(runs, flags_df)
    return runs, flags_df


if __name__ == "__main__":
    main()
