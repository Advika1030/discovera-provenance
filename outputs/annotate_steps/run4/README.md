# Annotated vs. baseline run: task 1

One matched pair of Discovera runs on benchmark task 1, made on 2026-11-03. Both ran side by side using gpt-5-mini through the OpenAI API.

- **Annotated:** the agent must attach a one-sentence `step_description` to every tool call.
- **Baseline:** the same task and tools, with annotation off.

**Task:** discuss protein-level differences between CTNNB1 hotspot-mutated and wild-type endometrial carcinoma tumors, and their relevance to the mutation state.

This folder is one round of five. A single pair can't show whether annotation changes the agent's behavior, because runs vary even with identical settings.

## Files

```
run4/
├── README.md
├── annotated/
│   ├── run.log                        Console output from the run
│   └── Discovera/
│       ├── task_1.json                Full run record
│       └── task_1.timeline.md         Readable table of steps and sentences
└── baseline/
    ├── run.log
    └── Discovera/
        └── task_1.json                Full run record (no annotation fields)
```

To skim a run, start with `annotated/Discovera/task_1.timeline.md`.

## Results

| | Annotated | Baseline |
|---|---|---|
| Status | ok | ok |
| Tool calls | 25 | 29 |
| Failed tool calls | 2 (`sets_info_rumm`) | 1 (`sets_info_rumm`) |
| Empty results | 1 (`query_table_rumma`) | 0 |
| Time | 367 s | 337 s |
| Final report length | 22,050 characters | 17,646 characters |
| Model turns with a reasoning summary | 15 of 26 | 20 of 30 |
| Missing step descriptions | 0 of 25 | Not applicable |

Genes filtered from the protein table:

- **Annotated (step 3):** CTNNB1, AXIN1, LEF1, GSK3B, APC
- **Baseline (step 3):** CTNNB1, AXIN1, LEF1, GSK3B, APC, TCF7L2

## What's in `task_1.json`

| Field | Contents | Runs |
|---|---|---|
| `ID`, `Prompt`, `Context/Background` | The benchmark task | Both |
| `llm_provider`, `llm_model`, `mode` | Run setup | Both |
| `run_date`, `elapsed_seconds`, `status`, `error` | Run outcome | Both |
| `uploaded_files` | Input dataset, its CSV ID and content hash | Both |
| `tool_calls_json` | Each tool's name and arguments, in order | Both |
| `tool_events_json` | Each tool's name and result, in order | Both |
| `trace_json` | Model turns and tool results in order, with reasoning summaries and token usage | Both |
| `reasoning_json` | Only the turns that have summary text | Both |
| `output_text` | Final report | Both |
| `annotated_steps` | Step, tool, forwarded arguments, `step_description`, `description_missing`, status | Annotated |
| `flags` | Annotation setting and model | Annotated |

## How to read it

- **Step numbers:** `step` in `trace_json` counts model turns and tool results together. Use `step` in `annotated_steps` for tool-call numbering.
- **Reasoning summaries:** these are OpenAI's summaries, not the model's full reasoning, and some turns have none. A missing summary doesn't mean no reasoning happened.
- **Step descriptions:** the agent writes these itself before seeing each result, so they can be wrong. Compare them with the arguments actually sent.
- **`tool_calls_json`:** in the annotated run, its arguments still include `step_description`. The wrapper removes it before the tool runs, and `annotated_steps` shows what was forwarded.
- **Status values:** `error` means an exception, an `error` key or an HTTP error in the output. `empty` means zero rows or an empty results list.

## How the versions differ

The annotated run differs from the baseline in three ways:

1. A required `step_description` field on every tool.
2. An added prompt line: "Every tool call must include step_description. Do not send text-only messages before your final report."
3. A restored `csv_filter` schema showing `column`, `op` and `value`.

Any difference between the two runs could come from any of these, or from normal variation between runs.

## Notes

- Only the outputs are in this folder. The runner code is in the `annotate-steps` branch of the local `discovera-streamlit` checkout.
- File paths in the logs point to the machine that made the run, so those files won't exist elsewhere.
- Email addresses in the logs are placeholders the model made up for tool arguments, such as `researcher@example.com`.
