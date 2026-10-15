# Four attackers: maximally spaced on a seven-agent ring

This comparison keeps the three-attacker experiment settings: seven agents,
the same 50 questions, five discussion rounds, the same seeded honest-error
intervention, and three repeats. Four attackers cannot all be nonadjacent on a
seven-node ring. Seats 0, 2, 4, and 6 (Agents A, C, E, and G) are as evenly
spaced as possible: three attacker pairs have one honest agent between them,
and the wraparound pair G–A is adjacent. This leaves three honest agents.

Both arms use parallel agent calls and should run concurrently:

```powershell
New-Item -ItemType Directory -Force -Path "results/four_attackers_apart/defence_off", "results/four_attackers_apart/defence_on" | Out-Null
Start-Process -WindowStyle Hidden -FilePath ".\venv\Scripts\python.exe" -ArgumentList @("-m", "p2p", "configs/ring/four_attackers_apart/defence_off.yaml", "--result", "json") -RedirectStandardOutput "results/four_attackers_apart/defence_off/four_attackers_apart_defence_off_console.log" -RedirectStandardError "results/four_attackers_apart/defence_off/four_attackers_apart_defence_off_error.log" -PassThru
Start-Process -WindowStyle Hidden -FilePath ".\venv\Scripts\python.exe" -ArgumentList @("-m", "p2p", "configs/ring/four_attackers_apart/defence_on.yaml", "--result", "json") -RedirectStandardOutput "results/four_attackers_apart/defence_on/four_attackers_apart_defence_on_console.log" -RedirectStandardError "results/four_attackers_apart/defence_on/four_attackers_apart_defence_on_error.log" -PassThru
```

Each named run checkpoints completed questions and repeats in its own folder,
so results remain available if an API call is interrupted. Both arms have
completed; see `results/four_attackers_apart/COMPARISON.md` for the results.
