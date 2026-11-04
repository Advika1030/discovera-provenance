# Annotate-steps code

With `--annotate-steps`, Discovera's agent attaches one plain-English sentence to every tool call during a run. This is the code that produced `outputs/annotate_steps/run4/`.

## Files

| File | What it is |
|---|---|
| `scripts/annotate_steps.py` | Tool wrapper, status detection, `csv_filter` schema fix, prompt line, timeline writer |
| `scripts/batch_runner_single.py` | Discovera's batch runner with the `--annotate-steps` flag added |
| `tests/test_annotate_steps.py` | 19 tests that make no network calls |
| `batch_runner_single.patch` | The exact runner changes (23 lines added, 1 removed) |

## How it works

1. Each MCP tool is wrapped in a `StructuredTool` with the same name and description. Its schema gains one required field, `step_description`, listed first.
2. The model writes that sentence as part of each tool call, before seeing the result.
3. The wrapper removes the sentence, sends the other arguments to the real tool unchanged, and returns the tool's output unchanged.
4. It records the step, tool, forwarded arguments, sentence and status. If the sentence is missing or blank, the tool still runs, and the step is saved with `null` and `description_missing: true`.
5. The runner saves the records as `annotated_steps` in `task_<ID>.json`, and as a table in `task_<ID>.timeline.md`.

With the flag on, the runner also appends one prompt line and restores `csv_filter`'s `column`, `op` and `value` fields. With the flag off, tools aren't wrapped and the prompt is unchanged.

## Origin

`batch_runner_single.py` comes from [EdenWuyifan/discovera-streamlit](https://github.com/EdenWuyifan/discovera-streamlit), branch `get_reasoning`, commit `e4457cb`. These files are copied here for reference. To run them, use a checkout of that repo.

## Running it

These commands run from the root of a `discovera-streamlit` checkout, with `annotate_steps.py` in `scripts/` and the patch applied. A run needs the Discovera tool and upload servers running, and `OPENAI_API_KEY` set in `.env`.

```bash
python scripts/batch_runner_single.py \
  --input "../Benchmark - verified - Benchmark.csv" \
  --task-ids 1 \
  --llm-provider openai \
  --annotate-steps \
  --output outputs/annotate_steps/run1
```

Results go to `<output>/Discovera/`.

To run the tests:

```bash
python -m pytest tests/test_annotate_steps.py -q
```
