# Verified facts about the benchmark log format

Checked directly against all 555 log files under `logs/Benchmark Logs (MCQ1207)/`
and against the tool source in `../discovera/src/discovera_fastmcp/server.py` and
`../discovera/src/baseline_fastmcp/server.py`. Nothing below is assumed — each
point was confirmed by reading code or running a check over every file.

1. **`tool_calls_json[i]` and `tool_events_json[i]` pair up by index for all 555
   files** — no length mismatches anywhere. Safe to `zip()` them.

2. **The top-level `status` and `error` fields are not useful signals.**
   `status == "ok"` in 100% of files and `error is None` in 100% of files —
   even for runs with zero tool calls, or runs containing internal tool
   errors. All real success/failure signal lives inside each
   `tool_events_json[i]["payload"]`.

3. **Tool error payload shape** (from `_exception_payload` in `server.py`):
   ```json
   {"error": {"tool": ..., "type": ..., "message": ..., "traceback": ...},
    "context": {...}}
   ```
   Test for a failed step is `"error" in payload`.

4. **There is no single key name for "the ID this step produced."** Traced
   every tool:
   - `csv_record` → id at the top level of the payload
   - `csv_filter` / `csv_select` / `csv_join` / `csv_aggregate` → nested under
     `payload["storage_entry"]`
   - `gsea_pipe` → `payload["gsea_result_metadata"]` and
     `payload["gsea_plot_metadata"]` (two outputs: a results CSV and a plot)
   - `ora_pipe` → `payload["ora_result_metadata"]`
   - `run_deseq2_gsea_pipe` / `run_deseq2_ora_pipe` → `payload["deseq2_result_metadata"]`
     **and** `payload["gsea"]["gsea_result_metadata"]` (nested two levels deep)

   The one constant across every one of these: the dict always has **both**
   `"id"` and `"path"` keys (that's what `_register_file` /
   `_save_dataframe_csv` always return). The parser finds produced IDs by
   **recursively scanning each payload for any dict containing both keys**,
   rather than hardcoding a key-path per tool.

5. **Exactly 5 parameter names ever carry a consumed storage ID** (grepped
   every tool signature in both server files): `csv_id`, `left_csv_id`,
   `right_csv_id`, `raw_counts_csv_id`, and bare `id` (used by `csv_read` and
   `storage_get`). The parser matches on these exact names.

   This matters for the deliberately-fake ID case
   (`output_o4_mini_1212/Discovera/task_6.json`, step 6): the fake id is
   `"1765565900_XXXXXXXXXXXXXXXX"` — literal `X` characters, not hex. A
   detector based on the *shape* of a real id (timestamp + hex suffix) would
   miss this. Name-based matching on `csv_id` catches it correctly.

6. **Tool inventory**: Discovera has ~20 tools (CSV tools, `gsea_pipe`,
   `ora_pipe`, the combined `run_deseq2_*` tools, Rummagene/literature lookup
   tools, `storage_list`/`storage_get`). Baseline has exactly 6: `csv_record`,
   `csv_read`, `csv_filter`, `csv_select`, `csv_join`, `csv_aggregate`.

7. **`payload["rows"]` is a JSON string, not a list** — needs a second
   `json.loads()` to get actual row dicts.

8. **`uploaded_files` entries have no `id`.** They only connect to a
   `csv_record` step by matching `csv_url` (allowing for the `<url>...`
   wrapper bug seen in `output_o4_mini_1212/Baseline/task_3.1.json` and
   `task_14.3.json`), never by name.

9. **Manually confirmed all 4 sanity-check cases** reproduce under this
   parsing model:
   - `Discovera/task_3.2` → 0 tool calls, yet `output_text` explicitly
     describes running Reactome ORA.
   - `Discovera/task_6`, step 6 → `gsea_pipe` called with fake id
     `1765565900_XXXXXXXXXXXXXXXX` → `FileNotFoundError`.
   - `Discovera/task_9.3` → 41 calls, `KeyError: 'log2FC'`, two
     `"Malformed response JSON: 'data'"` errors.
   - `Baseline/task_3.1` and `task_14.3` → `csv_record` fails with
     `ValueError: Failed to read CSV from URL: No connection adapters were
     found for '<url>https://...'`.
