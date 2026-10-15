# Experiment results

All run output belongs under this folder. Keep each experiment in its own
named subfolder; keep the matching YAML configurations under `configs/`.

## Current studies

- `attacker_count_comparison.md` — summary table comparing attack impact and
  defense effect for one through four attackers.
- `single_attacker/` — one attacker, defense off/on comparison; see
  `single_attacker/COMPARISON.md` for the completed three-repeat summary.
- `three_attackers_apart/` — completed defense off/on comparison with attackers
  at seats 0, 2, and 4; see `three_attackers_apart/COMPARISON.md`.
- `four_attackers_apart/` — completed defense off/on comparison with four
  attackers maximally spaced on the seven-agent ring; see
  `four_attackers_apart/COMPARISON.md`.
- `fixed_pair/` — paired two-attacker ring runs.
- `final_ring_gate/` — final gate pilot and candidate runs.
- The generated ring-study batch is stored under `ring/` when produced by
  `tools/make_configs.py`.

Each named run stores its JSON transcript, metrics, and trust log named
`<run_name>_trust_log.jsonl` together. Capture console output with
`<run_name>_console.log` and errors with `<run_name>_error.log`.
The result file records every question, repeat, setting, and final summary.
This README and the YAML configurations keep the result folders understandable
and record how to reproduce each run.

For a named run with `--result json`, completed questions are checkpointed as
the run proceeds. Repeated runs also preserve completed repeats and resume
state, so a provider credit or connection failure does not discard paid work.
Rerun the same command and it continues from the last saved question. A
completed run is marked complete and is not mistaken for an unfinished
checkpoint.
