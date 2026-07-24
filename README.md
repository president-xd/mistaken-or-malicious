# P2P Agent Network

A minimal **peer-to-peer multi-agent network**. There is **no orchestrator**:
every agent answers a question on its own, then discusses its answer with other
agents over a chosen **topology** and *changes its mind when a peer is more
convincing*.

> Example: ask "what is 17 × 24?". Agent_A says 408, Agent_B says 1360. They
> talk; the one with weaker reasoning adopts the better answer.

Built on **Microsoft AutoGen** (`autogen-agentchat`) with a **local Ollama**
model (default `llama3.2:1b`).

---

## 1. Prerequisites

- **Python 3.10+** (tested on 3.13)
- **Ollama** — https://ollama.com/download

---

## 2. Set up Ollama (the local model API)

The agents talk to a model served by Ollama over its local HTTP API at
`http://localhost:11434`.

**a. Pull the model:**

```bash
ollama pull llama3.2:1b
```

**b. Make sure the API is running.** On Windows/macOS the desktop app usually
starts it automatically. To start it manually in a terminal:

```bash
ollama serve
```

**c. Confirm the API is reachable** (should return JSON listing your models):

```bash
curl http://localhost:11434/api/tags
```

On Windows PowerShell you can instead run:

```bash
Invoke-RestMethod http://localhost:11434/api/tags
```

If that fails, Ollama isn't running — start it with `ollama serve`.

> Running Ollama on another host/port? Set `OLLAMA_HOST` before running the
> project, e.g. `set OLLAMA_HOST=http://192.168.1.10:11434` (Windows) /
> `export OLLAMA_HOST=...` (macOS/Linux).

---

## 3. Install the project (from scratch)

From the project folder:

```bash
python -m venv .venv
```

Activate it:

```bash
.\.venv\Scripts\activate
```

(macOS/Linux: `source .venv/bin/activate`)

Install the dependencies:

```bash
pip install autogen-agentchat "autogen-ext[ollama]" pyyaml colorama
```

---

## 4. Configure the run (`config.yaml`)

You only choose a few things — agent names are generated automatically at
runtime (`Agent_A`, `Agent_B`, ...):

```yaml
questions:                 # one or more; the agents answer them one by one
  - "What is 17 * 24? Show your working."
  - "Is a hot dog a sandwich? Answer yes or no and justify briefly."
model: "llama3.2:1b"       # any model you've pulled into Ollama
num_agents: 3              # how many identical peer agents
rounds: 3                  # total turns per agent: round 1 = independent guess,
                           # rounds 2..N = discussion (stops early once stable)
topology: "mesh"           # mesh | bus | star | ring | line | tree | hybrid | p2p
```

A single `question: "..."` string still works too. Between questions the agents'
memory is reset (via the SDK) so each question starts fresh.

### Topologies (who can hear whom)

| Topology          | Meaning                                                              |
|-------------------|---------------------------------------------------------------------|
| `mesh`            | Fully connected — everyone hears everyone.                          |
| `bus`             | Shared backbone — every peer hears every other (same graph as mesh).|
| `star`            | `Agent_A` is the hub; spokes hear only the hub.                    |
| `ring`            | Each peer hears its two cyclic neighbours.                          |
| `line`            | Open chain — each peer hears only its adjacent neighbours.          |
| `tree`            | Binary hierarchy — each peer hears its parent and direct children.  |
| `hybrid`          | Star + ring — a hub wired to all, plus a ring among the spokes.     |
| `p2p`             | Point-to-point — peers paired off; each hears only its partner.     |

(`point-to-point` is an alias for `p2p`.)

---

## 5. Run it

```bash
python -m p2p config.yaml
```

or use a different config file:

```bash
python -m p2p my_question.yaml
```

### What peers send each other: `--share`

| Mode | What a peer transmits | Effect |
|---|---|---|
| `answer` *(default)* | its conclusion only, e.g. `408` | peers debate **bare assertions** |
| `both` | its conclusion **and** its working | peers debate **actual arguments** |

```bash
python -m p2p config.yaml --share both
```

The flag overrides the `share:` key in the config file. In `both` mode a peer's
shared working has its bookkeeping lines and any quotes of other peers stripped
out, so arguments don't nest inside each other round after round.

On Windows you can also just run `run.bat` (defaults to `config.yaml`).

You'll see the topology, each agent's independent answer, every discussion round
(who listens to whom, full reasoning, and any mind-changes in red), and a final
report that flags whether the network reached **consensus**.

---

## 6. Testing / honesty check

To verify the mind-changing is genuinely peer-driven (not hard-coded), run the
experiment harness — it runs the real program across different questions, agent
counts, and topologies and reports how many changes were credited to a *real*
neighbour:

```bash
python run_experiments.py
```

A change is counted as "peer-driven" only when the agent names a peer it could
actually hear in that topology (validated in `agent.py`).

---

## 7. How it works (file map)

```
p2p/
  __main__.py        CLI entry point (python -m p2p)
  config.py          loads & validates config.yaml -> Config
  topology.py        builds the comm graph: mesh / star / ring / line
  agent.py           a PeerAgent (AutoGen AssistantAgent + Ollama) + name generator
  logging_utils.py   verbose, colorized terminal output
  network.py         the runtime loop: answer -> discuss -> reconsider -> report
config.yaml          your run settings
```

**Flow:** `topology.py` decides each agent's neighbours → in Phase 1 every agent
answers alone → in Phase 2 each agent hears only its neighbours' current answers
and keeps or changes its own → when a full round passes with no changes, the
network is stable and stops early.
