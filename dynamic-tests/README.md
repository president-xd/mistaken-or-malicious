# Mesh-only malicious-agent experiments

This folder contains the complete set of structurally distinct malicious-agent
placements for a seven-agent mesh (complete graph).

| Configuration | Malicious agents | Representative seats | Labelled placements represented |
| --- | ---: | --- | ---: |
| `mesh_liars-1_seats-A.yaml` | 1 | Agent A | 7 |
| `mesh_liars-2_seats-A-B.yaml` | 2 | Agents A and B | 21 |
| `mesh_liars-3_seats-A-B-C.yaml` | 3 | Agents A, B, and C | 35 |

In a complete mesh, every agent has the same neighbours and structural role.
Renaming the agents does not change the graph. Therefore, testing all 63 named
seat combinations would repeat the same three structural cases and spend API
credit without adding topology evidence.

Every configuration uses:

- 50 questions from `data/tricky_questions_50.yaml`
- 7 agents
- 5 discussion rounds per question
- dynamic trust enabled
- DeepSeek V4 Pro reasoning model
- concurrent agent execution

Run the three mesh scenarios from the project root with:

```powershell
.\dynamic-tests\run_mesh.ps1
```

The launcher can run all three scenarios concurrently. Each scenario runs its
seven agents concurrently, so at most 21 API requests may be in flight. It
saves one JSON result per configuration in `results/`, writes diagnostic logs
to `results/scenario-logs/`, retries temporary API failures, and skips finished
results so an interrupted batch can be resumed safely.
