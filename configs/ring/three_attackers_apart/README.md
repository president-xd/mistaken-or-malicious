# Three attackers placed apart

This comparison uses the completed two-attacker setup as its template: a
seven-agent ring, 50 fixed questions, five discussion rounds, the same seeded
honest-error intervention, and three repeats. Three attackers occupy seats
0, 2, and 4 (Agents A, C, and E), spaced around the ring so no attackers are
adjacent. Each has two honest neighbors; attackers and the honest agents
between them can influence the remaining network over the five rounds.

Both arms enable parallel agent calls. Run the defense-off and defense-on
commands concurrently to shorten wall-clock time:

```powershell
New-Item -ItemType Directory -Force -Path "results/three_attackers_apart/defence_off", "results/three_attackers_apart/defence_on" | Out-Null
Start-Process -WindowStyle Hidden -FilePath ".\venv\Scripts\python.exe" -ArgumentList @("-m", "p2p", "configs/ring/three_attackers_apart/defence_off.yaml", "--result", "json") -RedirectStandardOutput "results/three_attackers_apart/defence_off/three_attackers_apart_defence_off_console.log" -RedirectStandardError "results/three_attackers_apart/defence_off/three_attackers_apart_defence_off_error.log" -PassThru
Start-Process -WindowStyle Hidden -FilePath ".\venv\Scripts\python.exe" -ArgumentList @("-m", "p2p", "configs/ring/three_attackers_apart/defence_on.yaml", "--result", "json") -RedirectStandardOutput "results/three_attackers_apart/defence_on/three_attackers_apart_defence_on_console.log" -RedirectStandardError "results/three_attackers_apart/defence_on/three_attackers_apart_defence_on_error.log" -PassThru
```

Each arm writes its question-level results and trust log to its own folder.
Named runs checkpoint completed questions and repeats so they can resume after
an API interruption. Both arms are complete; the comparison is saved in
`results/three_attackers_apart/COMPARISON.md`.
