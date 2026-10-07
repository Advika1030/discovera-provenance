"""
Layer 1: parse Discovera/Baseline benchmark logs into structured tables and
per-run provenance graphs.

Background on the log format is recorded in NOTES.md (one level up) — read
that first if anything here looks surprising. The short version:

- Each log file has `tool_calls_json[i]` and `tool_events_json[i]` paired by
  index (verified across all files).
- A tool step "consumes" a prior table when one of its args is named
  csv_id / left_csv_id / right_csv_id / raw_counts_csv_id / id.
- A tool step "produces" a table whenever its payload contains a nested dict
  with BOTH an "id" and a "path" key — that's the one shape every storage
  entry shares, no matter which tool produced it or how deeply it's nested.
- A step "failed" when its payload contains an "error" key. The log's own
  top-level status/error fields are always "ok"/None and tell us nothing.

Run this directly to (re)generate outputs/runs.csv, outputs/steps.csv, and
outputs/lineage/<run>.json for every log under logs/Benchmark Logs (MCQ1207)/.
"""

import json
from pathlib import Path
from urllib.parse import urlsplit

import networkx as nx
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = REPO_ROOT / "logs" / "Benchmark Logs (MCQ1207)"
OUTPUTS_DIR = REPO_ROOT / "outputs"

# The only argument names that ever carry a reference to a previously-produced
# storage id (confirmed by grepping every tool signature in server.py — see
# NOTES.md point 5).
INPUT_ID_KEYS = {"csv_id", "left_csv_id", "right_csv_id", "raw_counts_csv_id", "id"}


def extract_input_ids(args):
    """Recursively find every value stored under a known id-parameter key."""
    found = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in INPUT_ID_KEYS and isinstance(value, str):
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(args)
    return found


def extract_output_entries(payload):
    """Recursively find every dict with both "id" and "path" keys.

    This is the universal shape returned by the server's storage-registration
    helpers (_register_file / _save_dataframe_csv), so it catches produced
    tables no matter which top-level key they're nested under (NOTES.md
    point 4: storage_entry, gsea_result_metadata, gsea.gsea_result_metadata,
    etc.) without hardcoding a path per tool.
    """
    found = []

    def walk(node, key_path):
        if isinstance(node, dict):
            if "id" in node and "path" in node:
                found.append(
                    {
                        "id": node["id"],
                        "name": node.get("name"),
                        "path": node.get("path"),
                        "source_key": key_path or "__root__",
                        "is_plot": "plot" in key_path.lower(),
                    }
                )
            for key, value in node.items():
                walk(value, f"{key_path}.{key}" if key_path else key)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{key_path}[{i}]")

    walk(payload, "")
    return found


def extract_error(payload):
    """Return the inner error dict if this step failed, else None."""
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        return payload["error"]
    return None


def strip_url_wrapper(url):
    """Undo the '<url>...' wrapping bug seen in some Baseline logs so we can
    still match a wrapped csv_url back to its uploaded_files entry."""
    if not isinstance(url, str):
        return url
    text = url.strip()
    if text.lower().startswith("<url>"):
        text = text[len("<url>"):]
    if text.lower().endswith("</url>"):
        text = text[: -len("</url>")]
    return text.strip()


def urls_match(a, b):
    """Compare two URLs, falling back to scheme+host+path (ignoring the
    signed-query-string part) if the exact strings don't match."""
    a, b = strip_url_wrapper(a), strip_url_wrapper(b)
    if a == b:
        return True
    pa, pb = urlsplit(a or ""), urlsplit(b or "")
    return (pa.scheme, pa.netloc, pa.path) == (pb.scheme, pb.netloc, pb.path)


def parse_one_log(path: Path):
    """Parse a single task_<id>.json log into a structured run dict."""
    data = json.loads(path.read_text())

    folder = path.parent.parent.name  # e.g. "output_o4_mini_1212"
    mode_from_path = path.parent.name  # "Baseline" or "Discovera"
    mode = data.get("mode") or mode_from_path
    if mode != mode_from_path:
        print(f"  [warn] mode mismatch in {path}: json says {mode!r}, "
              f"folder says {mode_from_path!r}")

    task_id = str(data.get("ID"))
    task_id_from_name = path.stem.removeprefix("task_")
    if task_id != task_id_from_name:
        print(f"  [warn] task id mismatch in {path}: json ID={task_id!r}, "
              f"filename says {task_id_from_name!r}")

    run_id = f"{folder}__{mode}__task_{task_id}"

    calls = data.get("tool_calls_json") or []
    events = data.get("tool_events_json") or []
    steps = []
    for i, (call, event) in enumerate(zip(calls, events)):
        payload = event.get("payload")
        steps.append(
            {
                "index": i,
                "tool": call.get("name"),
                "args": call.get("args") or {},
                "input_ids": extract_input_ids(call.get("args") or {}),
                "output_entries": extract_output_entries(payload),
                "error": extract_error(payload),
            }
        )

    return {
        "run": run_id,
        "folder": folder,
        "mode": mode,
        "model": data.get("llm_model"),
        "task_id": task_id,
        "run_date": data.get("run_date"),
        "elapsed": data.get("elapsed_seconds"),
        "output_text": data.get("output_text") or "",
        "uploaded_files": data.get("uploaded_files") or [],
        "steps": steps,
    }


def load_all_runs():
    """Parse every log file under LOGS_DIR into a list of run dicts."""
    paths = sorted(LOGS_DIR.glob("*/*/task_*.json"))
    return [parse_one_log(p) for p in paths]


def build_runs_table(runs):
    rows = []
    for run in runs:
        n_errors = sum(1 for s in run["steps"] if s["error"])
        rows.append(
            {
                "folder": run["folder"],
                "model": run["model"],
                "mode": run["mode"],
                "task_id": run["task_id"],
                "run_date": run["run_date"],
                "elapsed_seconds": run["elapsed"],
                "n_steps": len(run["steps"]),
                "n_errors": n_errors,
                "report_length": len(run["output_text"]),
            }
        )
    return pd.DataFrame(rows)


def build_steps_table(runs):
    rows = []
    for run in runs:
        for step in run["steps"]:
            output_ids = [e["id"] for e in step["output_entries"]]
            key_params = {k: v for k, v in step["args"].items() if k not in INPUT_ID_KEYS}
            error = step["error"]
            rows.append(
                {
                    "run": run["run"],
                    "step_index": step["index"],
                    "tool": step["tool"],
                    "input_ids": ";".join(step["input_ids"]),
                    "key_params": json.dumps(key_params, sort_keys=True),
                    "output_ids": ";".join(output_ids),
                    "error_type": error.get("type") if error else "",
                    "error_message": error.get("message") if error else "",
                }
            )
    return pd.DataFrame(rows)


def build_lineage_graph(run):
    """Build one PROV-style provenance graph for a single run.

    Node types: uploaded_file, data_table, tool_step, report, agent_run.
    Edge relation "used": activity -> entity it consumed.
    Edge relation "wasGeneratedBy": entity -> activity that produced it.
    Edge relation "wasInformedBy": tool_step -> agent_run (this step was part
      of this overall run).

    A step referencing an id that was never produced (e.g. a hallucinated or
    malformed id) still gets a "used" edge, pointing at a "missing:<id>"
    placeholder node — this makes broken lineage visible in the graph itself,
    on top of the UNKNOWN_INPUT_ID flag in checks.py.
    """
    g = nx.DiGraph()

    agent_run_node = "agent_run"
    g.add_node(agent_run_node, type="agent_run", run=run["run"], model=run["model"],
               mode=run["mode"], task_id=run["task_id"], run_date=run["run_date"])

    for i, uf in enumerate(run["uploaded_files"]):
        g.add_node(f"upload:{i}", type="uploaded_file", name=uf.get("name"), url=uf.get("url"))

    produced_nodes = set()  # storage ids already added as data_table nodes

    for step in run["steps"]:
        step_node = f"step{step['index']}_{step['tool']}"
        g.add_node(
            step_node,
            type="tool_step",
            tool=step["tool"],
            step_index=step["index"],
            args=json.dumps(step["args"], sort_keys=True),
            error=json.dumps(step["error"]) if step["error"] else "",
        )
        g.add_edge(step_node, agent_run_node, relation="wasInformedBy")

        # step used uploaded_file, when this is the csv_record call that
        # ingested it (matched by csv_url, not by name).
        if step["tool"] == "csv_record":
            csv_url = step["args"].get("csv_url")
            if csv_url:
                for i, uf in enumerate(run["uploaded_files"]):
                    if urls_match(csv_url, uf.get("url")):
                        g.add_edge(step_node, f"upload:{i}", relation="used")

        # step used each input table (or a missing placeholder, if the id
        # was never actually produced by an earlier step).
        for input_id in step["input_ids"]:
            if input_id not in produced_nodes:
                g.add_node(f"missing:{input_id}", type="missing_reference", id=input_id)
            target = input_id if input_id in produced_nodes else f"missing:{input_id}"
            g.add_edge(step_node, target, relation="used")

        # entity wasGeneratedBy step, for every table/plot this step produced.
        for entry in step["output_entries"]:
            g.add_node(
                entry["id"],
                type="data_table",
                name=entry["name"],
                path=entry["path"],
                source_key=entry["source_key"],
                is_plot=entry["is_plot"],
            )
            g.add_edge(entry["id"], step_node, relation="wasGeneratedBy")
            produced_nodes.add(entry["id"])

    g.add_node("report", type="report", length=len(run["output_text"]))
    g.add_edge("report", agent_run_node, relation="wasGeneratedBy")

    return g


def main():
    print(f"Loading logs from: {LOGS_DIR}")
    runs = load_all_runs()
    print(f"Parsed {len(runs)} runs")

    OUTPUTS_DIR.mkdir(exist_ok=True)
    lineage_dir = OUTPUTS_DIR / "lineage"
    lineage_dir.mkdir(exist_ok=True)

    runs_df = build_runs_table(runs)
    runs_df.to_csv(OUTPUTS_DIR / "runs.csv", index=False)
    print(f"Wrote {OUTPUTS_DIR / 'runs.csv'} ({len(runs_df)} rows)")

    steps_df = build_steps_table(runs)
    steps_df.to_csv(OUTPUTS_DIR / "steps.csv", index=False)
    print(f"Wrote {OUTPUTS_DIR / 'steps.csv'} ({len(steps_df)} rows)")

    for run in runs:
        g = build_lineage_graph(run)
        out_path = lineage_dir / f"{run['run']}.json"
        with open(out_path, "w") as f:
            json.dump(nx.node_link_data(g), f, indent=2)
    print(f"Wrote {len(runs)} lineage graphs to {lineage_dir}")

    return runs


if __name__ == "__main__":
    main()
