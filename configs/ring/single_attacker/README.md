# One-attacker comparison

This pair keeps the completed two-attacker setup's network, question set,
round count, and repeat count, with one attacker at seat 0. Run each arm with
JSON recording enabled:

```powershell
.\venv\Scripts\python.exe -m p2p configs/ring/single_attacker/defence_off.yaml --result json
.\venv\Scripts\python.exe -m p2p configs/ring/single_attacker/defence_on.yaml --result json
```

Outputs go to `results/single_attacker/defence_off/` and
`results/single_attacker/defence_on/`. Both arms completed all three repeats.
The comparison is recorded in `results/single_attacker/COMPARISON.md`.

Both configs use a stable `run_name` and `skip_done: true`. An interrupted
plain repeat run checkpoints completed questions and repeats; rerunning its
command resumes it, while a finished run is skipped.
