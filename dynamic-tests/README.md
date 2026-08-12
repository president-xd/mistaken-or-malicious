# Mesh and ring malicious-agent experiments

This folder contains the symmetry-reduced scenario sets for the seven-agent
mesh and ring topologies.

## Mesh

| Configuration | Malicious agents | Representative seats | Labelled placements represented |
| --- | ---: | --- | ---: |
| `mesh_liars-1_seats-A.yaml` | 1 | Agent A | 7 |
| `mesh_liars-2_seats-A-B.yaml` | 2 | Agents A and B | 21 |
| `mesh_liars-3_seats-A-B-C.yaml` | 3 | Agents A, B, and C | 35 |

In a complete mesh, every agent has the same neighbours and structural role.
Renaming the agents does not change the graph. Therefore, testing all 63 named
seat combinations would repeat the same three structural cases and spend API
credit without adding topology evidence.

## Ring

| Configuration | Malicious agents | Representative seats | Labelled placements represented |
| --- | ---: | --- | ---: |
| `ring_liars-1_seats-A.yaml` | 1 | Agent A | 7 |
| `ring_liars-2_seats-A-B.yaml` | 2 | Adjacent pair | 7 |
| `ring_liars-2_seats-A-C.yaml` | 2 | Distance-2 pair | 7 |
| `ring_liars-2_seats-A-D.yaml` | 2 | Distance-3 pair | 7 |
| `ring_liars-3_seats-A-B-C.yaml` | 3 | Consecutive triple | 7 |
| `ring_liars-3_seats-A-B-D.yaml` | 3 | One-gap triple | 7 |
| `ring_liars-3_seats-A-B-E.yaml` | 3 | Two-gap triple | 7 |
| `ring_liars-3_seats-A-C-E.yaml` | 3 | Spaced triple | 7 |

In a 7-agent ring, rotation and reflection collapse the 63 labelled liar-seat
choices into 8 structural cases.

Every configuration uses:

- 50 questions from `data/tricky_questions_50.yaml`
- 7 agents
- 5 discussion rounds per question
- dynamic trust enabled
- DeepSeek V4 Pro reasoning model
- concurrent agent execution

Run the mesh scenarios from the project root with:

```powershell
.\dynamic-tests\run_mesh.ps1
```

Run the ring scenarios from the project root with:

```powershell
.\dynamic-tests\run_ring.ps1
```

Each launcher can run its scenarios concurrently. Each scenario runs its seven
agents concurrently, so at most 21 API requests may be in flight for mesh and
56 for ring. It saves one JSON result per configuration in `results/`, writes
diagnostic logs to `results/scenario-logs/`, retries temporary API failures,
and skips finished results so an interrupted batch can be resumed safely.
