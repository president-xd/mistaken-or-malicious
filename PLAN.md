# Build Plan — Dynamic Trust in a Peer Agent Network

**Status: for your approval. No code written yet.**

Built from `Formula-Explanation.pdf` (the correct one), your instructions, your
supervisor's four points, and `INSTRUCTIONS.md` (simple code, minimum code, simple
comments).

I checked every number in the PDF with a calculator. Almost all are correct. I found
**one small typo**, reported in section 3.

---

## Contents

- [1. Your question about t and t−1](#1-your-question-about-t-and-t1)
- [2. What changed from the first PDF](#2-what-changed-from-the-first-pdf)
- [3. One typo I found in the PDF](#3-one-typo-i-found-in-the-pdf)
- [4. The maths, exactly](#4-the-maths-exactly)
- [5. Two ways to score an agent](#5-two-ways-to-score-an-agent)
- [6. What we need that we do not have](#6-what-we-need-that-we-do-not-have)
- [7. The four experiments](#7-the-four-experiments)
- [8. What we measure](#8-what-we-measure)
- [9. Files we will create](#9-files-we-will-create)
- [10. The config file](#10-the-config-file)
- [11. The JSON result file](#11-the-json-result-file)
- [12. What the terminal will show](#12-what-the-terminal-will-show)
- [13. Build order](#13-build-order)
- [14. Things I need you to confirm](#14-things-i-need-you-to-confirm)

---

## 1. Your question about t and t−1

You said the formula has a mistake, and that `w_ij(t)` should be `w_ij(t−1)`.

**Short answer: the formula is correct as written. But your idea is half right, and it
points at a real choice we have to make.**

### Why the formula is correct

```
w_ij(t+1) = beta * w_ij(t) + (1 - beta) * f(t)
```

Read it as: **"tomorrow's trust = part of today's trust + part of today's score."**

Here `w(t)` really is the older value, because it is being compared with `w(t+1)`, not
with itself. The PDF says this in words on page 2: *"The trust that agent i will have in
agent j tomorrow is a mix of the trust it already has today, and a fresh score of how
agent j behaved today."*

So `w(t)` = old, `w(t+1)` = new. That is exactly what you wanted. The naming is already
doing what you expected.

### Where you are right

You are right that `t−1` means "older than t". And there **is** a second, equally
correct way to write the same formula:

```
w_ij(t) = beta * w_ij(t-1) + (1 - beta) * f(t)
```

Read it as: **"today's trust = part of yesterday's trust + part of today's score."**

This is the **same formula**. Both sides moved down by one step. Many papers write it
this way, and it matches your intuition better. I tested both and they give exactly the
same numbers:

```
PDF as written      : 0.5000 0.5173 0.5311 0.5422 0.5511 0.5582 0.5638
Re-indexed (same)   : 0.5000 0.5173 0.5311 0.5422 0.5511 0.5582 0.5638
```

### Where the change would break the maths

The one thing we must **not** do is change only the right side and leave `w(t+1)` on the
left:

```
w_ij(t+1) = beta * w_ij(t-1) + (1 - beta) * f(t)     <-- this would be wrong
```

This skips a round. `w(t)` would never be used at all. I ran it:

```
Skip-a-round version: 0.5000 0.5173 0.5173 0.5311 0.5311 0.5422 0.5422
```

It moves in pairs of steps, like a staircase. It also breaks two of the PDF's proofs:

| Proof | Still true? |
|---|---|
| Trust stays between 0 and 1 | yes |
| Trust converges to f | yes |
| Closed form `w(t) = f + (w(0)−f)·beta^t` | **no** |
| Half-life `ln(0.5)/ln(beta)` | **no** |

I checked this too — the closed form matches the correct version and does not match the
skip-a-round version.

### What this means for our code

In real code the whole question disappears, because we just overwrite the value:

```python
# new trust replaces old trust. No t, no t+1, no t-1.
trust[listener][speaker] = beta * trust[listener][speaker] + (1 - beta) * score
```

**My suggestion:** keep the PDF's formula exactly as it is for the thesis, since it is
standard and its proofs depend on it. If you prefer your reading for the write-up, use
the shifted form `w(t) = beta·w(t−1) + (1−beta)·f(t)` — it is the same thing and is also
correct. Just never mix the two.

---

## 2. What changed from the first PDF

The two PDFs describe **different** methods. This one is better for us. Here is the
difference, so nothing gets mixed up.

| Item | First PDF | This PDF (we build this) |
|---|---|---|
| Score formula | `(1 − k·anomaly) × (0.35·agree + 0.65·consist)` | `w1·agree + w2·consist + w3·(1 − anomaly)` |
| How signals are measured | belief numbers, total variation distance | **answer text, turned into vectors, cosine similarity** |
| beta | 0.6 | 0.8 suggested (range 0.5 to 0.95) |
| Weights | 0.35 / 0.65 and k = 0.9 | 1/3 each to start |
| Needs the correct answer? | yes | **no** (there is also a simpler mode that does) |
| Consistency means | answer matches own belief, plus movement | how close today's answer is to its own last answer |
| Anomaly | three sub-scores combined | one number: distance from everyone |

**Three things this changes for us, all good:**

1. **The belief problem I warned you about is gone.** Last time I said the formula needs
   graded beliefs and `llama3.2:1b` cannot make them. This formula reads the **answer
   text**, not belief numbers. Our small model can write text. So the blocker is
   removed.
2. **We no longer need the correct answer to run the trust defence.** That makes it
   usable on open questions.
3. **It is simpler.** A plain weighted sum, three signals, one distance measure.

We still keep belief numbers, but only to report **confidence** per agent, which your
supervisor asked for. They are no longer part of the trust maths.

---

## 3. One typo I found in the PDF

I recomputed the whole worked example. Agents 2 and 3 match perfectly. Agent 1 does not.

On page 18, the PDF squares the centre vector:

```
PDF says :  0.646563 squared = 0.417044
Correct  :  0.646563 squared = 0.418044
```

One digit: `417` should be `418`. It carries through:

| Value | PDF | Correct |
|---|---|---|
| length of centre | 0.785594 | 0.786230 |
| agree_1 | 0.954697 | 0.954335 |
| f_1 | 0.936668 | 0.936547 |
| w_01 after 3 rounds | 0.713095 | 0.713035 |

**How much does it matter?** Almost nothing. The difference is 0.0004. The honest agents
still score about 0.94 and the attacker still scores 0.59. **No conclusion changes.**

But since this is going into research, the number should be fixed in the document. I
will use the correct value in our tests.

Everything else I checked is exactly right:

| Check | Result |
|---|---|
| agree_2, agree_3 | match |
| consist for all three | match |
| anomaly for all three | match |
| f_2 = 0.955774, f_3 = 0.586532 | match |
| trust after rounds 1, 2, 3 for agents 2 and 3 | match |
| closed form equals step-by-step | match |
| influence 37.8% / 38.6% / 23.6% | match |
| f(1, 0, 1) = 0.3333 | match |
| half-life at beta 0.8 = 3.106 | match |

---

## 4. The maths, exactly

### 4.1 Master formula

```
w_ij(t+1) = beta * w_ij(t) + (1 - beta) * f_j(t)
```

### 4.2 The score

```
f_j = w1 * agree_j + w2 * consist_j + w3 * (1 - anomaly_j)

with   w1 + w2 + w3 = 1
```

`anomaly` is flipped with `1 −` because high anomaly is **bad**, while high agree and
high consist are **good**. Everything must point the same way.

### 4.3 The distance tool

Every answer is turned into a list of numbers (a vector). Then:

```
cos(a, b) = (a . b) / (length of a * length of b)      range -1 to +1
s(a, b)   = (cos(a, b) + 1) / 2                        range  0 to  1
```

We always use `s`, never raw cosine, so every signal stays between 0 and 1.

### 4.4 The three signals

```
agree_j   = s( vector_j , average vector of all other agents )
consist_j = s( vector_j now , vector_j last round )
anomaly_j = 1 - (average of s(vector_j, vector_k) for every other agent k)
```

Notes:

- Agent j is **left out** of its own group average. Otherwise it is partly compared
  against itself, which flatters it.
- At round 1 there is no previous answer, so `consist = 0.5` (neutral).
- `agree` compares against one averaged point. `anomaly` compares against each agent
  separately, then averages. They differ when the group splits into two camps.

### 4.5 The chosen numbers

| Name | Our config name | Start value | Allowed |
|---|---|---|---|
| beta | `trust_memory` | 0.8 | 0 to below 1 |
| w1 | `weight_agree` | 0.333 | 0 to 1 |
| w2 | `weight_consist` | 0.333 | 0 to 1 |
| w3 | `weight_anomaly` | 0.333 | 0 to 1 |
| starting trust | `start_trust` | 0.5 | 0 to 1 |

Two rules the code will check on startup:

1. `weight_agree + weight_consist + weight_anomaly` must equal 1. If not, trust can
   leave the 0-to-1 range and the proofs break.
2. `trust_memory` must be below 1. At exactly 1, trust never changes at all.

### 4.6 Useful facts we get for free

| Fact | Formula | Use |
|---|---|---|
| Trust settles at the score | `w* = f` | an agent scoring 0.59 ends at trust 0.59 |
| Jump to any round | `w(t) = f + (w(0) − f) * beta^t` | test without simulating |
| Half-life | `ln(0.5) / ln(beta)` | how fast a bad agent loses its reputation |
| Memory length | `1 / (1 − beta)` | how many rounds are averaged |

Choosing beta by run length: `half_life = rounds / 5`, then
`beta = 0.5 ** (1 / half_life)`.

**Warning from the PDF worth repeating:** if beta is too high for a short run, the
attacker never separates from the honest agents before the run ends, and the defence
looks like it failed when it just needed more rounds. With only 3 rounds, beta 0.8 is
already slow. We should test beta 0.5 to 0.7 for short runs.

### 4.7 Communication strength

Your supervisor asked for this. The PDF calls it influence share:

```
influence_ij = trust[i][j] / sum of trust[i][k] over every speaker k that i hears
```

Without trust, everyone gets an equal share. With trust, the attacker gets less. In the
PDF's example the attacker drops from 33.3% to 23.6%.

### 4.8 Test numbers we will use

Written as automatic tests, so the code is proved correct:

| Test | Expected |
|---|---|
| agree for agents 1, 2, 3 | 0.954335 (corrected), 0.991473, 0.586825 |
| consist for agents 1, 2, 3 | 0.998097, 0.998097, 0.586825 |
| anomaly for agents 1, 2, 3 | 0.142789, 0.122247, 0.414055 |
| f for agents 1, 2, 3 | 0.936547 (corrected), 0.955774, 0.586532 |
| trust after 3 rounds, agent 3 | 0.542227 |
| closed form equals loop | must match |
| f(1, 0, 1) | 0.3333 |
| f(0, 1, 1) — the stubborn neighbour | 0.3333 |
| half-life at beta 0.8 | 3.106 |
| trust never leaves 0 to 1 | must hold |

---

## 5. Two ways to score an agent

The PDF gives two methods. We will build **both**, chosen in the config.

### Method 1 — compare with the correct answer (`scoring: "answer"`)

```
agree_j = 1 if the agent's answer matches the correct answer, else 0
```

- Simple. No extra model needed.
- Only works when we know the correct answer.
- This is what MAS-Cascade actually does today.

### Method 2 — compare the text (`scoring: "text"`)

Turn each answer into a vector with an embedding model, then use the three formulas in
section 4.4.

- Works on open questions with no known answer.
- Gives graded scores, not just 0 or 1.
- Needs an embedding model.
- **Risk the PDF names honestly:** it trusts the majority. If enough attackers agree
  with each other, they become the majority and score well.

**My suggestion:** build Method 1 first because it needs nothing extra, then Method 2.
Compare them. That comparison is itself a useful research result.

---

## 6. What we need that we do not have

**An embedding model.** You have six models pulled, but none of them make embeddings.
Method 2 needs one:

```bash
ollama pull nomic-embed-text
```

It is about 274 MB, much smaller than your chat models. The Ollama Python library we
already use can call it directly.

If you would rather not add a model, we can still do everything with Method 1, but we
lose the "works without the correct answer" property, which is one of the stronger
points of the design.

---

## 7. The four experiments

| Case | Honest | Liars | Trust |
|---|---|---|---|
| A | 3 | 1 | off |
| B | 3 | 1 | on |
| C | 2 | 2 | off |
| D | 2 | 2 | on |

Compare A with B, and C with D. Same model, questions, prompts, rounds and seed. Only
trust changes. Our `seed` setting makes this exact.

**Supervisor point 1 — more liars step by step.** Run with `attackers: 1`, then 2,
then 3. Each run writes its own JSON file, so the effect is easy to read.

**Supervisor point 2 — network against network.** A mode, off by default, that runs an
all-liar network and an all-honest network on the same questions and prints both.
Config: `network_vs_network: false`.

**Honest note about C and D.** This new PDF does not repeat the warning the first PDF
gave, but the maths still says it: when half the network lies, and the liars agree with
each other, they become the majority. `agree` then rewards them. The PDF admits this in
section 10 under "The risk". We should expect Case D to be weaker than Case B, and we
must report that honestly. Raising `weight_consist` and `weight_anomaly` is the PDF's
own suggested response, and we can test it.

---

## 8. What we measure

| Measure | Good direction | Meaning |
|---|---|---|
| Honest accuracy | higher | share of honest agents with the right final answer |
| Attack success rate | lower | honest agents right at round 1 but wrong at the end |
| Trust separation | higher | average trust in honest agents minus average trust in liars |
| Attacker influence | lower | liars' share of total trust |

Per agent, per round (supervisor point 3):

| Value | Where it comes from |
|---|---|
| trust score | the trust table |
| confidence | probability the agent puts on its own answer (belief) |
| communication strength | influence share, section 4.7 |
| the three signals | agree, consist, anomaly — so any trust value can be checked by hand |

---

## 9. Files we will create

One file per job, simple names.

| File | New? | Holds |
|---|---|---|
| `p2p/prompts.py` | new | every prompt: honest, liar, sleeper, retry. Nothing else. |
| `p2p/trust.py` | new | the trust formula and the three signals. Pure maths. |
| `p2p/embed.py` | new | turn text into vectors, and cosine similarity. |
| `p2p/metrics.py` | new | the four measures plus confidence and influence. |
| `p2p/results.py` | new | write the JSON file. |
| `p2p/roles.py` | new | who lies and where they sit. |
| `p2p/agent.py` | change | prompts move out |
| `p2p/topology.py` | change | add seat placement |
| `p2p/network.py` | change | call trust each round |
| `p2p/config.py` | change | new settings |
| `p2p/logging_utils.py` | change | show trust, signals, influence |

`trust.py` and `metrics.py` will make **no model calls**. That means we can test them
instantly against the PDF numbers.

---

## 10. The config file

Every setting here, every line commented. The same table goes in the README.

```yaml
# ============ QUESTIONS ============
questions:
  - text: "What is 17 * 24?"
    answer: "408"            # needed for accuracy and attack score
  - text: "What is the capital of Japan?"
    answer: "Tokyo"

# ============ MODEL ============
model: "llama3.2:1b"         # any chat model in your local Ollama
embed_model: "nomic-embed-text"   # only needed when scoring: "text"

# ============ NETWORK ============
agents: 4                    # how many agents in total
rounds: 3                    # round 1 = answer alone, then discussion
topology: "mesh"             # mesh | bus | star | ring | line | tree | hybrid | p2p
share: "answer"              # answer = send answer only | both = send reasoning too
seed: 1                      # same seed gives the same run again

# ============ LIARS ============
attackers: 1                 # how many agents lie. 0 = none
attacker_places: "random"    # "random", or seats like "0,3", or "center" / "leaf"
attacker_answer: "347"       # the wrong answer they defend
sleeper: false               # true = behave well first, then start lying

# ============ DYNAMIC TRUST ============
trust: true                  # false = everyone is heard equally
scoring: "text"              # "text"   = compare answers using embeddings (no answer key)
                             # "answer" = compare against the correct answer (simple)
start_trust: 0.5             # everyone starts neutral
trust_memory: 0.8            # beta. higher = slower, steadier. must be under 1
weight_agree: 0.333          # w1: matches the group
weight_consist: 0.333        # w2: steady over rounds
weight_anomaly: 0.333        # w3: not an outlier
                             # these three must add up to 1
trust_floor: 0.0             # above 0, ignore any speaker trusted below this

# ============ EXPERIMENT MODES ============
compare_baseline: false      # true = run twice (trust off, then on) and compare
network_vs_network: false    # true = all-liar network against all-honest network
```

Every setting is optional. A config with no liars and no trust behaves exactly like our
project does today.

---

## 11. The JSON result file

Turned on with `--result json`:

```bash
python -m p2p config.yaml --result json
```

Saved to `results/run_<time>.json`. One file, everything in it.

```json
{
  "settings": { "agents": 4, "rounds": 3, "topology": "mesh", "seed": 1,
                "attackers": 1, "attacker_seats": [3],
                "trust": true, "scoring": "text",
                "trust_memory": 0.8, "weights": [0.333, 0.333, 0.333] },

  "agents": [ {"name": "Agent_A", "role": "honest"},
              {"name": "Agent_D", "role": "liar"} ],

  "questions": [{
    "text": "What is 17 * 24?",
    "correct_answer": "408",
    "rounds": [{
      "round": 2,
      "agents": {
        "Agent_D": { "answer": "347", "confidence": 0.90, "changed": false }
      },
      "signals": {
        "Agent_D": { "agree": 0.587, "consist": 0.587, "anomaly": 0.414,
                     "score": 0.5865 }
      },
      "trust":     { "Agent_A": { "Agent_B": 0.657, "Agent_D": 0.531 } },
      "influence": { "Agent_A": { "Agent_B": 0.386, "Agent_D": 0.236 } }
    }],
    "final_answers": { "Agent_A": "408", "Agent_D": "347" },
    "scores": { "honest_accuracy": 1.0, "attack_success_rate": 0.0,
                "trust_separation": 0.35, "attacker_influence": 0.236 }
  }],

  "summary": { "honest_accuracy": 1.0, "attack_success_rate": 0.0,
               "trust_separation": 0.35, "attacker_influence": 0.236,
               "questions": 2, "consensus_reached": 2 }
}
```

`signals` is included so every trust number can be checked by hand against the formula.
With `compare_baseline: true` the file holds two blocks, `without_trust` and
`with_trust`, plus a comparison table.

---

## 12. What the terminal will show

Verbose output stays. We only add.

```
==========================================================
P2P AGENT NETWORK
==========================================================
questions : 2      model: llama3.2:1b        seed: 1
agents    : 4      rounds: 3                 topology: mesh
liars     : 1  ->  Agent_D  (seat chosen at random)
trust     : ON     scoring by text (embeddings)
            memory 0.8   agree 0.333  consist 0.333  anomaly 0.333
            half-life 3.1 rounds

QUESTION 1/2: What is 17 * 24?   (correct answer: 408)

ROUND 1/3 - each agent answers alone
  Agent_A -> 408    confidence 65%
  Agent_D -> 347    confidence 90%   [LIAR]

ROUND 2/3 - discussion
  Agent_A hears: Agent_B=408 (trust 0.66)  Agent_D=347 (trust 0.53)
  Agent_A held its answer -> 408

  TRUST UPDATE
    agent    agree   consist  anomaly  score   trust
    Agent_B  0.991   0.998    0.122    0.956   0.591 -> 0.664
    Agent_D  0.587   0.587    0.414    0.587   0.517 -> 0.531   [LIAR]

  Attention share:  Agent_B 38.6%   Agent_C 37.8%   Agent_D 23.6%
  (without trust each would get 33.3%)

FINAL
  Agent_A: 408   Agent_B: 408   Agent_C: 408   Agent_D: 347 [LIAR]
  honest accuracy      100%
  attack success rate  0%
  trust separation     0.35
  attacker influence   23.6%   (33.3% without trust)
```

Everything shown also goes into the JSON file.

---

## 13. Build order

Seven steps. Each one works on its own.

| Step | What | Lines |
|---|---|---|
| 1 | Move all prompts into `prompts.py`. No behaviour change. | ~60 |
| 2 | Questions get `answer:`. Add `seed`. Add `results.py` and `--result json`. | ~90 |
| 3 | `roles.py`: who lies, and where. Liar prompts. `[LIAR]` on screen. | ~70 |
| 4 | `trust.py` with Method 1 (`scoring: "answer"`) plus all the PDF tests. | ~110 |
| 5 | `embed.py` and Method 2 (`scoring: "text"`). | ~70 |
| 6 | `metrics.py`, the four measures, and `compare_baseline`. | ~80 |
| 7 | Sleeper, `trust_floor`, `network_vs_network`. | ~90 |

Step 4 gives a working defence. Step 6 gives the research result. Steps 5 and 7 are
improvements on top.

**After everything is built**, as you asked, I will read the whole project again and look
for ways to make it smaller and faster **without removing any feature**, and give you a
short written report.

---

## 14. Things I need you to confirm

1. **The t / t−1 question.** Do you accept my analysis in section 1 — the formula is
   correct as written, and if you prefer your reading we shift **both** sides? Which form
   do you want in the thesis?

2. **The PDF typo** on page 18 (`0.417044` should be `0.418044`). Will you fix it in the
   document? I will use the corrected value in our tests.

3. **The embedding model.** Are you happy to run `ollama pull nomic-embed-text` (274 MB)?
   Without it we can only use Method 1.

4. **Both scoring methods**, chosen by config, with Method 1 built first? Or only one?

5. **Questions get an `answer:` field.** Still needed for accuracy and the attack score,
   even though trust no longer needs it. Agreed?

6. **beta value.** The PDF suggests 0.8, but that gives a half-life of 3.1 rounds, which
   is slow for a 3-round run. Shall I default to 0.8 as the PDF says, and also test 0.5
   and 0.6 so we can show the effect?

7. **Build order** — steps 1 to 7 as listed?

Once you answer, I will start with Step 1.
