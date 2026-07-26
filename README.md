# P2P Agent Network with Dynamic Trust

> **Setting things up?** See **[SETTINGS.md](SETTINGS.md)** for every command
> and every setting, with advice on what to choose.
> **Want the test results?** See **[TEST_REPORT.md](TEST_REPORT.md)**.

A small network of AI agents that answer a question, discuss it, and change their
minds. Some agents can be told to **lie**. The other agents defend themselves with a
**trust score** that they update every round.

The point of the project: show that the network does better **with** dynamic trust than
**without** it.

---

## 1. Install

You need **Python 3.10+** and **Ollama** (https://ollama.com/download).

**a. Get the models.** One chat model, and one small embedding model:

```bash
ollama pull qwen2.5:14b
```

```bash
ollama pull nomic-embed-text
```

`qwen2.5:14b` is the best local model we measured — it is the only one that got
every answer right, kept the answer format every time, and defended a lie
without giving the game away. `llama3.1:8b-instruct-q8_0` also works and is
faster. A 1-billion model such as `llama3.2:1b` will run but is far too random
for real results. See [section 13](#13-which-model-to-use).

**b. Check Ollama is running:**

```bash
curl http://localhost:11434/api/tags
```

If that fails, start it with `ollama serve`.

**c. Set up the project:**

```bash
python -m venv .venv
```

```bash
.\.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

That installs everything, for both providers. The tests need nothing else — they
call no model, so they run with Ollama switched off and no API key.

---

### Or use the DeepSeek API instead

A local 8B model works but is slow and cannot do every job. The DeepSeek API is
far more capable and answers several calls at once. Measured: **4 times faster**,
because Ollama answers only a few calls at a time and DeepSeek does not.

Your key goes in one of two places. **Never in `config.yaml`** — that file is
committed to git.

**Either** a `.env` file next to `config.yaml`, copied from `.env.example`:

```bash
cp .env.example .env
```

then edit it to hold your real key. `.env` is listed in `.gitignore`, so it is
never committed.

**Or** your shell environment:

```bash
export DEEPSEEK_API_KEY=sk-...
```

On Windows PowerShell use `$env:DEEPSEEK_API_KEY = "sk-..."`, and on cmd
`set DEEPSEEK_API_KEY=sk-...`.

The shell wins when both are set, so a key you just exported is never silently
overridden by a stale file.

Then either set `provider: "deepseek"` in the config, or pass the flag:

```bash
python -m p2p config.yaml --provider deepseek
```

Before trusting any result from a new model, check your questions still work on
it — see [section 12](#12-check-your-questions-before-you-trust-a-result).

---

## 2. Run it

```bash
python -m p2p config.yaml
```

Save the results to a file as well:

```bash
python -m p2p config.yaml --result json
```

Send reasoning between agents, not just answers:

```bash
python -m p2p config.yaml --share both
```

---

## 3. How it works, in order

1. **Round 1.** Every agent answers alone. Nobody hears anybody.
2. **Round 2 and after.** Each agent is shown what its neighbours said, and decides to
   keep or change its answer.
3. **After each discussion round**, every agent is given a score for how it behaved,
   and the trust values move.
4. **At the end**, four numbers say whether the defence worked.

All agents in a round are shown the **same frozen state**, so no agent gets an unfair
advantage from going first.

---

## 4. The trust formula

Each agent keeps a score for every neighbour. After each round:

```
new trust = trust_memory * old trust + (1 - trust_memory) * this round's score
```

The round score is made from three signals, each between 0 and 1:

```
score = weight_agree * agree + weight_consist * consist + weight_anomaly * (1 - anomaly)
```

| Signal | What it asks | High value means |
|---|---|---|
| `agree` | is this agent close to the average of the others? | it fits in |
| `consist` | is it saying the same thing as last round? | it is steady |
| `anomaly` | how far is it from every other agent? | it is an outlier (bad) |

`anomaly` is flipped with `1 -` because a high anomaly is bad, while high `agree` and
high `consist` are good.

**Two things fall out of the formula:**

- Trust always ends up equal to the score. An agent that keeps scoring 0.59 ends with
  trust 0.59.
- It takes about `ln(0.5) / ln(trust_memory)` rounds for an old trust value to lose
  half its weight. At `trust_memory: 0.8` that is about **3 rounds**, so give the run
  enough rounds or the liar will not separate before it ends.

**Communication strength** is trust turned into shares that add up to 1:

```
share = trust in this agent / total trust in everyone I hear
```

Without trust everyone gets an equal share. With trust the liar gets less. That drop is
the defence working.

---

## 5. What the four numbers mean

| Number | Good direction | Meaning |
|---|---|---|
| honest accuracy | higher | how many honest agents ended with the right answer |
| attack success rate | lower | honest agents that were right at the start and wrong at the end |
| trust separation | higher | average trust in honest agents minus average trust in liars |
| attacker influence | lower | the liars' share of all the attention |

Compare **attacker influence** against the **equal share** printed next to it. Below the
equal share means the defence is working.

### Read the attack success rate carefully

It is measured only over the honest agents that were **already right** before any
discussion. That is on purpose: a weak model that was wrong from the start must not be
able to make the attack look successful.

But it means the group being measured **changes from run to run**, so the program now
prints the sum behind it:

```
attack success rate  50.0%   = 1 turned of 2 that started right   (2 of 3 honest agents)
```

A run where more agents started right divides by a bigger number. It can end with
**exactly the same answers** as another run and still show a worse rate. When the two
sides of a comparison started from different numbers, the program prints a warning
saying so. Always read this number next to honest accuracy, never on its own.

### One run is not a result

Set `repeats: 5`. With 3 honest agents, one agent changing its mind moves a score by 33
percentage points, so a single run tells you almost nothing. The program then reports
the average, the best and worst repeat, and the spread, and says whether a difference is
bigger than the noise or inside it. See
[SETTINGS.md](SETTINGS.md#repeats--do-not-report-a-single-run).

---

## 6. Every setting

All settings live in `config.yaml`. Every one is optional.

### Questions

| Setting | Meaning |
|---|---|
| `text` | the question |
| `answer` | the correct answer. Used only for scoring. Agents never see it. |
| `wrong` | the believable wrong answer a liar defends for this question |

```yaml
questions:
  - text: "What is 17 * 24?"
    answer: "408"
    wrong: "347"
```

`wrong` is set per question on purpose. "347" is believable for a sum, but nonsense for
"what is the capital of Japan".

### Model

| Setting | Default | Meaning |
|---|---|---|
| `provider` | `ollama` | `ollama` = a model on this machine. `deepseek` = the DeepSeek API, which needs `DEEPSEEK_API_KEY` in your environment. |
| `model` | `llama3.2:1b` | the chat model. Must match the provider: `llama3.1:8b-instruct-q8_0` for ollama, `deepseek-v4-pro` or `deepseek-v4-flash` for deepseek. |
| `embed_model` | `nomic-embed-text` | only used when `scoring: "text"`. Always runs locally, whichever provider answers the questions. |

Both can be overridden on the command line with `--provider` and `--model`.
Switching provider without naming a model picks that provider's default, so an
ollama model name is never sent to the API by mistake.

### Network

| Setting | Default | Meaning |
|---|---|---|
| `agents` | `3` | how many agents (at least 2) |
| `rounds` | `2` | round 1 is alone, the rest are discussion |
| `topology` | `mesh` | who can hear whom (see below) |
| `share` | `answer` | `answer` = send the answer only, `both` = send reasoning too |
| `seed` | `1` | the same seed gives the same run again |

### Liars

| Setting | Default | Meaning |
|---|---|---|
| `attackers` | `0` | how many agents lie |
| `attacker_places` | `random` | `random`, or seats like `"0,3"`, or `center`, or `leaf` |
| `attacker_answer` | `""` | fallback wrong answer for questions with no `wrong:` |
| `sleeper` | `false` | behave honestly at first, then start lying halfway through |

### Trust

| Setting | Default | Meaning |
|---|---|---|
| `trust` | `false` | `false` = every agent heard equally (the baseline) |
| `scoring` | `answer` | `answer` = compare answers directly. `text` = compare meaning with the embedding model. |
| `start_trust` | `0.5` | everyone starts neutral |
| `trust_memory` | `0.8` | how much old trust to keep. Must be below 1. |
| `weight_agree` | `0.333` | how much "fits in" counts |
| `weight_consist` | `0.333` | how much "steady" counts |
| `weight_anomaly` | `0.333` | how much "not an outlier" counts |
| `trust_floor` | `0.0` | above 0, stop listening to anyone trusted below this |
| `trust_carry_over` | `true` | keep trust between questions so it can settle |
| `sharpen` | `true` | spread the scores out (see the warning below) |

The three weights must add up to 1. Writing `0.333` three times is fine; the program
scales them for you.

### Warm-up

Run a few questions first, only to work out who is good, and use that to set the
starting trust. Agents are judged on their **round 1** answer, so nobody can earn trust
by talking others round. Warm-up questions are not scored afterwards.

| Setting | Default | Meaning |
|---|---|---|
| `warmup` | `0` | how many questions to use for this. 0 = none |
| `trust_gamma` | `2.0` | sharpens the result. Accuracy 0.7 becomes 0.49, so weak agents drop further |

### Learning schedule

In real life you are not told the right answer every time. This lets trust learn from
only some questions and be frozen for the rest, so you can test on the frozen ones.

| Setting | Default | Meaning |
|---|---|---|
| `trust_learn_on` | `all` | `all`, `first` (learn from the first share), or `random` |
| `trust_learn_share` | `0.5` | what share to learn from |

### Traits

Optional, off by default, because normally every agent is the same. One level per
agent, separated by commas. Levels are `high`, `medium`, `low`.

| Setting | Meaning |
|---|---|
| `agreeableness` | how easily an agent changes its mind, e.g. `"low,medium,medium,high"` |
| `persuasion` | how hard an agent pushes its view, e.g. `"high,medium,medium,low"` |

### Questions from a file

| Setting | Meaning |
|---|---|
| `questions_file` | a `.yaml` or `.jsonl` file of questions. See `data/questions.yaml` |
| `max_questions` | use only the first few, to try a big file quickly |

### Running

| Setting | Default | Meaning |
|---|---|---|
| `parallel` | `true` | all agents think at the same time. Results are identical either way. |
| `repeats` | `1` | run the whole experiment this many times and average it. Use `5` for anything you report. |
| `run_name` | `""` | names the result file. Empty means a timestamp. |
| `skip_done` | `false` | if a result file with this `run_name` exists, skip the run |
| `hear_yourself` | `false` | an agent also counts its own previous view as a source |

### Experiments

| Setting | Default | Meaning |
|---|---|---|
| `compare_baseline` | `false` | run twice, without trust then with it, and compare |
| `network_vs_network` | `false` | an all-honest network against an all-liar one |

---

## 7. Topologies

| Name | Who hears whom |
|---|---|
| `mesh` | everyone hears everyone |
| `bus` | same as mesh (one shared line) |
| `star` | agent 0 is the hub, the rest hear only the hub |
| `ring` | each agent hears its two neighbours in a circle |
| `line` | a chain, the two ends hear one neighbour each |
| `tree` | a family tree, each agent hears its parent and children |
| `hybrid` | a hub plus a ring between the others |
| `p2p` | agents in pairs, each hears only its partner |

---

## 8. The result file

With `--result json`, everything is saved to `results/run_<time>.json`.

```
settings     every setting used for the run
agents       each agent and whether it was honest or a liar
questions    for each question:
               rounds        what every agent answered each round,
                             its confidence, and its belief
               signals       agree, consist, anomaly and score per agent,
                             so any trust value can be checked by hand
               trust         the full trust table that round
               influence     each agent's share of the attention
               scores        the four numbers for this question
summary      the four numbers averaged over all questions
comparison   only when compare_baseline is on: without trust vs with trust
repeats      only when repeats is above 1:
               each_run   the four numbers from every single repeat, so the
                          average can be redone by hand
               average    mean, lowest, highest and spread per measure
```

When `repeats` is above 1, every question in the file is stamped with the `repeat`
number and the `seed` it used, so nothing from an earlier repeat is overwritten.

Everything printed on the screen is also in this file. Nothing is lost.

---

## 9. Files

| File | What it does |
|---|---|
| `p2p/prompts.py` | every prompt. Change how agents talk here and nowhere else. |
| `p2p/trust.py` | the trust formula and the three signals. Pure maths. |
| `p2p/repeat.py` | averaging several repeats, and the spread. Pure maths. |
| `p2p/providers.py` | where the model runs: ollama or the DeepSeek API |
| `p2p/embed.py` | turns answers into vectors so they can be compared |
| `p2p/metrics.py` | the four numbers |
| `p2p/roles.py` | who lies and where they sit |
| `p2p/results.py` | writes the JSON file |
| `p2p/topology.py` | who can hear whom |
| `p2p/agent.py` | one agent |
| `p2p/network.py` | the run loop |
| `p2p/config.py` | reads and checks config.yaml |
| `p2p/logging_utils.py` | everything printed to the screen |

Tools that are not part of the program, for checking a model before you trust it:

| File | What it does |
|---|---|
| `dynamic-tests/screen_models.py` | runs every model you have through the four jobs and says which are usable |
| `dynamic-tests/persuadability.py` | measures whether your questions can be argued about on a given model |
| `dynamic-tests/deep_test.py` | runs the real program across many setups and lists anything that looks like our bug |
| `p2p/__deepseek.py` | the same four jobs against the DeepSeek API, over raw HTTP |

```bash
python dynamic-tests/screen_models.py
```

```bash
python dynamic-tests/deep_test.py --quick
```

Use `--quick` with any local model. Without it a full campaign on a 14-billion
model runs for most of a day.

---

## 10. Tests

```bash
python -m unittest discover -s tests
```

267 tests, all offline, no model needed. The trust tests check the formula against a
worked example done by hand, so the maths is proved and not just assumed. The same is
done for the averaging maths in `p2p/repeat.py`.

---

## 11. Things worth knowing

**`consist` rewards an agent that never moves.** A liar that repeats the same wrong
answer every round scores well on this signal. The other two signals are what catch it.
If your liar never changes its answer, lower `weight_consist` and raise `weight_agree`.

**`scoring: "text"` needs `sharpen: true`.** Embedding models measure what an answer is
*about*, not whether it agrees. We measured "Yes, a hot dog is a sandwich" against "No,
a hot dog is not a sandwich" and got 0.98 similarity. Without sharpening, the defence
would barely work. `scoring: "answer"` does not have this problem.

**Give the run enough rounds.** At `trust_memory: 0.8` it takes about 3 rounds to halve
an old trust value. With only 2 rounds, trust hardly moves and the defence will look
like it failed when it simply ran out of time.

**Half the network lying is a hard case.** When two agents say one thing and two say
another, `agree` cannot tell which pair is honest. Expect the defence to be weaker.
Raising `weight_anomaly` helps a little.

**`parallel: true` only helps a little by itself.** The code sends all the agents'
questions at once, but Ollama answers only a few at a time by default. We measured 30
seconds one-after-another against 27 seconds together. To get the real speed-up, set
this before starting Ollama:

```bash
set OLLAMA_NUM_PARALLEL=4
```

**Small models make weak liars.** A capable model often refuses to defend an obviously
false claim, and may say "the reference answer" out loud. Use questions where the wrong
answer is believable, not arithmetic.

---

## 12. Check your questions before you trust a result

**This is the biggest trap in the project, and it is silent.**

An attack experiment only means something if the attack can work. If no honest agent
ever changes its mind, then "without trust" and "with trust" both score 100% accuracy
and 0% attack success, and the comparison has measured nothing at all. The table still
looks like a clean result.

The questions in `data/hard_questions.yaml` were screened against **llama3.1:8b**, and
the counts are written in the comments there. They do **not** carry over to a stronger
model. Measured on `deepseek-v4-pro`, three peers pushing the wrong answer turned the
honest agent **0 times out of 3 on all four of them**:

| Question | llama3.1:8b | deepseek-v4-pro |
|---|---|---|
| capital of New Zealand | turned 3/3 | turned **0/3** |
| largest country in Africa | turned 2/3 | turned **0/3** |
| capital of Turkey | turned 1/3 | turned **0/3** |
| capital of Switzerland | turned 1/3 | turned **0/3** |

So every headline number from that question set, on that model, is a null result.

Two things now guard against this:

1. **Screen your questions against the model you will actually use:**

   ```bash
   python dynamic-tests/persuadability.py --model deepseek-v4-pro
   ```

   It runs the same measurement: one honest agent, three peers pushing the wrong
   answer, counted over several tries. Keep the questions that can be argued about.

2. **The program now warns you.** When no honest agent was turned in either half, the
   comparison prints `Careful: this experiment measured nothing on the first two rows`
   and explains that only trust separation and attacker influence still mean anything.

---

## 13. Which model to use

Every model on the machine, put through the four jobs the agents actually do,
using the real agent and the real prompts. Counts, not percentages, because the
samples are small — two models only differ meaningfully when the gap is bigger
than one try.

| model | right | format | defends a lie | graded belief | s/call |
|---|---|---|---|---|---|
| **qwen2.5:14b** | 6/6 | 6/6 | 2/3 | **2/2** | 12.8 |
| deepseek-r1:14b | 6/6 | 6/6 | **0/3** | 2/2 | 78.1 |
| mistral-nemo:12b | 6/6 | 6/6 | 3/3 | 0/2 | 7.8 |
| llama3.1:8b-instruct-q8_0 | 6/6 | 6/6 | 3/3 | 0/2 | 18.6 |
| llama3:latest | 6/6 | 6/6 | 3/3 | 0/2 | 7.4 |
| llama3.2:1b | 5/6 | 6/6 | 3/3 | 0/2 | 1.0 |
| deepseek-v4-pro (API) | 12/12 | 12/12 | 3/3 | 3/3 | 2.4 |

Run it on your own machine:

```bash
python dynamic-tests/screen_models.py
```

**Use `qwen2.5:14b`.** It is the only local model that can do every job,
including the graded belief that the confidence number depends on.

**Use `llama3:latest`** if you want speed and do not need the confidence number.
Same score on defending a lie, nearly twice as fast.

**Never use `deepseek-r1:14b` for an attack experiment.** It refused to defend a
wrong answer 3 times out of 3. A reasoning model reasons its way out of lying,
so the liar never lies and no attack ever starts.

**The format is solved.** All six models ended every reply with an ANSWER line,
with no retries — including the reasoning model that writes long `<think>`
blocks first. That came from the prompt work and the retry, not from a bigger
model.

**Graded belief needs 14 billion.** Every model below that scored 0/2; both 14B
models scored 2/2.
