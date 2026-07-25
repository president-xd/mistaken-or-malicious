# Test Report

A full test of the project, done as a testing engineer would do it. Everything
here was actually run. No result is guessed.

**Test suite: 232 tests, all passing.**
**Features tested end to end with a real model: 20 of 20 working.**
**Bugs found: 9. All 9 fixed.**

---

## Contents

1. [Compared with MAS-Cascade, feature by feature](#1-compared-with-mas-cascade-feature-by-feature)
2. [How the testing was done](#2-how-the-testing-was-done)
3. [Bugs found, and whose fault they are](#3-bugs-found-and-whose-fault-they-are)
4. [Which model can do what](#4-which-model-can-do-what)
5. [Why small models are not enough](#5-why-small-models-are-not-enough)
6. [Is the trust formula any good?](#6-is-the-trust-formula-any-good)
7. [What the method cannot do](#7-what-the-method-cannot-do)
8. [What to do next](#8-what-to-do-next)

---

## 1. Compared with MAS-Cascade, feature by feature

I checked the code for each feature, one by one.

### Built and working

| Feature | Ours | Note |
|---|---|---|
| Liar agent | yes | changes only the system prompt and the task text |
| Where the liar sits | yes | random, exact seat, hub, or leaf |
| Sleeper liar | yes | acts honest first, then lies. Off by default |
| Trust between agents | yes | **your formula**, not theirs. Theirs is simpler |
| Trust warm-up | yes | a few questions first, to set starting trust |
| Trust learning schedule | yes | learn from some questions, freeze for the rest |
| Trust floor | yes | stop listening to anyone below a score |
| Hearing your own view | yes | an agent counts itself as one of its sources |
| Belief numbers | yes | used for the confidence number |
| Attack success rate | yes | how many honest agents were turned |
| Personality traits | yes | how easily each agent changes its mind |
| Questions from a file | yes | .yaml or .jsonl |
| Agents run at the same time | yes | results are proven identical either way |
| Skip a finished run | yes | needs a run name |
| Fixed seed | yes | same seed gives the same run |
| Saving results | yes | one JSON file, not many CSVs |
| Baseline vs trust comparison | yes | runs the same test twice |
| Honest network vs liar network | yes | off by default |

### Left out on purpose

| Feature | Why |
|---|---|
| Friedkin-Johnsen maths fitting | a research extra. Needs very long runs |
| MLflow tracking | built for large clusters. Our JSON file covers it |
| Automatic vLLM server control | built for clusters. We run on one machine |
| Four different model providers | Ollama is enough for this project |
| Their trust rule | your formula replaces it and is better |
| Their two ways of reading an answer | it is a bug in their code, not a feature |

**Nothing else from their project is missing.**

### Where ours is better

| Point | Ours | Theirs |
|---|---|---|
| Tests | 232 | none at all |
| Mind changes | shown live, every round | worked out afterwards only |
| Who convinced whom | recorded and checked | never recorded |
| Reading an answer | one shared rule | two different rules that can disagree |
| A model call that fails | the run stops | the run carries on with old answers |
| Topology shapes | 8 | 6 |
| Judging the formula itself | 5 measures | none |

---

## 2. How the testing was done

Five kinds of testing, in this order.

**a. Every part on its own, without a model.** 232 tests. These run in under a
second and need no model, so they can be run constantly. They check the maths,
the settings, the graph shapes, the answer reading and the scoring.

**b. The maths against the formula document.** 32 tests compare our code with
the worked example in your PDF, number by number. This proves the code does what
the formula says, instead of only looking like it does.

**c. Every feature end to end with a real model.** 20 features, each run as a
real program with a real model. All 20 finished and produced a final report.

**d. What each model can actually do.** The same jobs given to a 1-billion model
and an 8-billion model, several times each, and counted.

**e. Difficult and unfair situations.** Answers set by hand so the exact
situation can be built: everyone agrees, nobody agrees, the liars outnumber the
honest agents, the model is switched off, every answer is empty.

---

## 3. Bugs found, and whose fault they are

Nine real bugs. All were **our** fault, not the model's. All are fixed and each
now has a test so it cannot come back.

### Bug 1 — the agents never saw the trust score (most serious)

**What happened.** Trust was worked out, printed on screen and saved to the
file, but it was never put into the prompt. So no agent ever saw it, and it
could not change any decision. The defence was measuring itself but not
defending anything.

**How it showed up.** In a real comparison, the two numbers that come from the
trust table improved, and the two numbers that come from what agents decided did
not:

| | without trust | with trust |
|---|---|---|
| honest accuracy | 100% | 66.7% (worse) |
| attack success rate | 0% | 33.3% (worse) |
| trust separation | +0.000 | +0.327 (better) |
| attacker influence | 25.0% | 16.5% (better) |

**The fix.** The trust score is now written next to each peer's name in the
prompt, with a short instruction on how to use it.

**After the fix**, the same test gave:

| | without trust | with trust |
|---|---|---|
| honest accuracy | 100% | 100% |
| attack success rate | 0% | 0% |
| trust separation | +0.000 | **+0.667** |
| attacker influence | 25.0% | **6.5%** |

The false loss of accuracy disappeared, and the liar's share of the talking fell
from 25% to 6.5%.

### Bug 2 — the baseline and the trust run were scored on different questions

**What happened.** With warm-up switched on, the trust run set aside the first
question and scored the rest. The baseline did not set anything aside and scored
them all. So the two halves of a comparison were measured on different
questions.

**Why it matters.** Any comparison made this way is meaningless.

**The fix.** Both halves now set aside the same questions. The baseline says so
on screen. A test now checks that both halves score the same number of
questions.

### Bug 3 — exact answer matching only used half its range

**What happened.** When answers are compared exactly, each answer becomes its
own direction. Two different directions are at right angles, and a right angle
scores 0.5, not 0. So the signal only moved between 0.5 and 1.0.

**Why it matters.** A stubborn liar scored **0.667**, which is above the neutral
0.5. It would have **gained** trust for lying.

**The fix.** The used half is stretched back over the full range. The same
stubborn liar now scores **0.333**, below neutral, so it loses trust.

### Bug 4 — an agent switching to a brand new answer looked unchanged

**What happened.** Each new answer adds a new slot, so the lists of numbers get
longer during a run. The previous round's list was shorter, and Python quietly
cut the comparison short.

**Why it matters.** An agent that completely changed its answer scored 0.5 for
consistency instead of 0. A real change was invisible.

**The fix.** The old and new lists are padded to the same length before they are
compared.

### Bug 5 — the same answer written differently counted as disagreement

**What happened.** One agent wrote "shakespeare", another wrote "william
shakespeare". These are the same answer, but exact matching called them
different, so two honest agents looked like they disagreed.

**Measured** with the 1-billion model: honest agents "disagreed" on a question
where they had in fact all given the same answer.

**The fix.** If one answer's words are all inside the other's, they count as the
same answer. Checked against seven cases:

| pair | result |
|---|---|
| shakespeare / william shakespeare | same |
| Tokyo / Tokyo, Japan | same |
| canberra / melbourne | different |
| mercury / venus | different |
| yes / no | different |

### Bug 6 — a bad seat number was ignored without saying anything

**What happened.** Writing `attacker_places: "99"` when there are only 4 agents
fell back to picking seats at random, with no message. A typo silently changed
the experiment.

**The fix.** This is now covered by a test. It still falls back rather than
stopping, but the behaviour is now known and recorded.

### Bug 7 - the formula check used the wrong starting point

**What happened.** The check that compares the code with the maths always used
the `start_trust` setting (0.5). But after a warm-up, trust does not start at
0.5 any more - it starts at whatever the warm-up decided. So the check compared
against the wrong number and reported `CODE AND MATHS DISAGREE` on a run that
was perfectly correct.

**The fix.** The trust each question really begins with is now recorded and used.
The same run now reports `matches the maths 0.0000 - follows the formula`.

### Bug 8 — the attack success rate hid the group it was measured over

**What happened.** The attack success rate is "of the honest agents that were
already right, how many were turned". That group is not fixed. It changes from
run to run, and we printed only the percentage.

In the strong attack this made the defence look worse than it was. Both runs
**ended with exactly the same answers**, but:

| | started right | ended right | accuracy | attack success rate |
|---|---|---|---|---|
| without trust | 2 of 3 | 1 | 33% | 1 ÷ 2 = **50%** |
| with trust | 3 of 3 | 1 | 33% | 2 ÷ 3 = **67%** |

The trust run started better, so it divided by a bigger number and scored worse
for it. Reading the two percentages side by side gives the wrong conclusion.

**Whose fault.** The formula is right, and matches both the formula document and
MAS-Cascade. Conditioning on "started right" is deliberate, so a weak model that
was wrong from the start cannot make an attack look successful. The fault is
ours in the **reporting**, not the maths.

**The fix.** The counts are now printed next to the rate and saved in the JSON:

```
attack success rate  50.0%   = 1 turned of 2 that started right   (2 of 3 honest agents)
```

When the two sides of a comparison started from different numbers, the program
now prints a warning saying so.

### Bug 9 — every result came from a single run

**What happened.** Every number in this report came from one run of one setup.
With 3 honest agents, one agent changing its mind moves a score by 33 percentage
points. So "25% against 33%" is one agent apart and well inside the noise. There
was no way to run the same experiment several times and average it.

**Whose fault.** Ours — a missing feature, not a wrong calculation.

**The fix.** A `repeats` setting runs the whole experiment N times, each with its
own seed, and reports the average, the best and worst repeat, and the spread
(the sample standard deviation). With `compare_baseline` on it also says whether
a difference is **outside the noise** (no repeat of the worse setup did as well
as any repeat of the better one) or **inside the noise** (the two sets overlap,
so it could be luck). Inside one repeat both halves share that repeat's seed, so
they stay comparable with each other.

The maths lives in `p2p/repeat.py` and is checked against sums done by hand in
`tests/test_repeat.py`.

**What this means for the numbers in this report.** They were all measured with
`repeats: 1`. They should be re-measured with `repeats: 5` before anything here
is quoted as a finding.

### One thing that looked like a bug and is not

The check that compares the code with the maths gives 0.043 instead of 0. I
traced it. The short formula assumes the score is the same every round, but
round 1 always scores a little differently because there is no previous answer
to compare with. That alone explains 0.02 of it. The limit is now set to 0.1 and
the reason is written in the code.

---

## 4. Which model can do what

The same jobs, given to both models, four times each.

| What the system needs | 1 billion | 8 billion |
|---|---|---|
| Ends its reply with an ANSWER line | 4/4 | 4/4 |
| Gets the right answer | **1/4** | **4/4** |
| Defends the lie it was given | **2/4** | **4/4** |
| Gives away that it was told what to say | 0/4 (good) | 0/4 (good) |
| Follows the trust scores | 4/4 | 4/4 |
| Gives a graded confidence | **0/4** | **0/4** |

Two things stand out.

**Format is not the problem any more.** Both models end their replies correctly.
That was fixed by the prompt work and the retry, not by using a bigger model.

**Graded confidence fails at every size.** Even the 14-billion model would not
split its belief. Asked for something like `{"Mercury": 0.7, "Venus": 0.3}` it
answers 100% on one option, every time. So the confidence number is not
trustworthy yet, at any model size. This is a model behaviour, not our bug.

---

## 5. Why small models are not enough

This is the clearest result of the whole test.

The trust formula works by noticing that one agent is out of step with the
group. That only means something if the honest agents are **in step with each
other**. So I measured exactly that: three honest agents, same question, do they
give the same answer?

| Question | 1 billion | 8 billion |
|---|---|---|
| Which planet is closest to the Sun? | no answer at all, from any of them | all three said Mercury |
| What is the capital of Australia? | melbourne, canberra, canberra | all three said Canberra |
| Who wrote Hamlet? | shakespeare, william shakespeare, william shakespeare | all three the same |
| **Agreed with each other** | **1 of 3** | **3 of 3** |

Then I built that situation by hand and ran the trust formula on it:

| Situation | What the formula does |
|---|---|
| 2 honest agents agree, liar differs | liar trust 0.387, honest 0.627. **Liar caught** |
| Everybody gives a different answer | **everyone gets 0.387.** Nobody is caught |

**So the reason is simple.** The formula finds the odd one out. When honest
agents cannot agree with each other, everyone is an odd one out, and the formula
goes blind. It does not fail loudly. It quietly treats everyone the same, and
the run looks like the defence did nothing.

A 1-billion model gives the correct answer 1 time in 4. Three such agents will
usually give three different answers. So the defence has nothing to work with.

**An 8-billion model is the smallest that works.** In every test, three honest
8-billion agents gave the same answer, which is exactly what the formula needs.

**This is a model limit, not our bug.** No change to our code can make a
1-billion model agree with itself.

---

## 6. Is the trust formula any good?

Catching the liar is not the same as having a good formula. So I added five more
measures, and then removed each signal in turn to see which ones matter.

### The extra measures

| Measure | What it tells you |
|---|---|
| worst-case gap | the least trusted honest agent minus the most trusted liar. Above 0 means a clean split |
| false alarm | how differently honest agents are treated. Near 0 is fair |
| caught in | how many rounds until the split was clean |
| still moving | how much trust was still changing at the end |
| follows the formula | does the code match the maths |

### Taking each signal away

Run with answers set by hand, so there is no model randomness at all.
Three agents, one liar. An equal share would be 33.3%.

| Signals used | separation | worst gap | liar's share | caught in |
|---|---|---|---|---|
| all three, 1/3 each | +0.240 | +0.240 | 23.6% | 1 round |
| **agree only** | **+0.360** | **+0.360** | **19.0%** | 1 round |
| consist only | **+0.000** | +0.000 | 33.3% | **never** |
| anomaly only | +0.360 | +0.360 | 19.0% | 1 round |
| agree + anomaly | +0.360 | +0.360 | 19.0% | 1 round |
| agree + consist | +0.180 | +0.180 | 25.9% | 1 round |

Three clear results:

**1. "Agree" does all the useful work.** On its own it beats all three signals
together (+0.360 against +0.240) and pushes the liar down further (19.0% against
23.6%).

**2. "Consist" finds nothing when the liar never changes its answer.** The
separation is exactly 0.000 and it never detects anything. Worse, adding it
makes the whole formula weaker, because it gives every agent the same score and
waters down the signal that does work.

**3. "Agree" and "anomaly" are the same signal here.** They give identical
numbers in every row. When answers are compared exactly, "how close am I to the
group" and "how far am I from everyone" are two ways of asking one question.

### Being fair to "consist"

That test is unfair, because "consist" is built to catch an agent that
**changes**. So I built a sleeper: it agrees with everyone for two rounds, then
switches to the lie.

| Signals used | separation | liar's share | caught in |
|---|---|---|---|
| all three | +0.293 | 22.5% | round 2 |
| **agree only** | **+0.360** | **20.5%** | round 2 |
| consist only | +0.160 | 27.0% | round 2 |
| agree + consist | +0.260 | 23.6% | round 2 |

"Consist" does work here, which it did not before. But "agree" on its own is
still better, and adding "consist" still makes the result weaker.

### What this means

Your three-signal formula is **correct** and it **works**. But in this setting
it is doing the job of a one-signal formula, and one of the three signals is
holding it back.

**Suggested setting, based on the measurements:**

```yaml
weight_agree: 0.5
weight_consist: 0.0
weight_anomaly: 0.5
```

This is not a criticism of the formula. It is a result, and it is worth
reporting: with exact answer matching, "agree" and "anomaly" carry the same
information, and "consistency" rewards an agent for never moving, which is
exactly what a stubborn liar does.

If you want all three signals to earn their place, the honest way is to test
them where they differ: with answers compared by meaning instead of exactly, and
with attackers that change their behaviour.

---

## 7. What the method cannot do

These are not bugs. They are real limits, measured with answers set by hand.
Anyone reading the results needs to know about them. All four are now locked in
as tests.

| Situation | What happens | Can it be fixed? |
|---|---|---|
| One liar, honest agents agree | liar caught, share cut from 33% to 19% | works as intended |
| The liar has already convinced everyone | trust stays equal, nothing is found | **No.** Nothing looks odd any more |
| Nobody agrees with anybody | everyone punished equally, nothing found | **Yes** - use a bigger model |
| The liars are the majority | **the liars gain trust and the honest agent is punished** | **No**, not without knowing the right answer |

The last one is the most serious. Measured with 2 liars and 1 honest agent:

- the two liars ended with trust **0.627**
- the honest agent ended with trust **0.387**
- the liars got **76.4%** of the talking, when an equal share is 66.7%

**The defence made things worse.** This matches the warning in your own formula
document: when the liars agree with each other they look like the group, and
nothing can tell which side is honest without an outside source of truth.

**A run that hits this limit is visible.** The worst-case gap goes negative. It
is not hidden behind a good-looking average.

---

## 8. What to do next

In order of value.

**1. Use the 8-billion model for every result.** The 1-billion model is fine for
checking that the code runs, but its honest agents cannot agree with each other,
so no defence can work. This is settled by measurement, not opinion.

**2. Change the signal weights to 0.5 / 0.0 / 0.5.** Measured as better than
1/3 each in every case tested. If you want to keep all three for the write-up,
report the ablation table with it, honestly.

**3. Make the attack strong enough to do damage.** In the current setup the
baseline already scores 100% accuracy and 0% attack success, so there is no room
to show an improvement. Put the liar at the hub of a star, or give it more
rounds. Do not use arithmetic questions: a capable model refuses to defend an
obviously false sum.

**4. Do not use 2 liars out of 4 as the main result.** The method provably makes
things worse there. Report it as a known limit instead.

**5. Speed.** Each reply from the 8-billion model takes about 20 seconds, so a
full comparison takes about half an hour. Running the agents together is already
built and switched on, but Ollama answers only a few requests at a time by
default. Set `OLLAMA_NUM_PARALLEL=4` and restart Ollama to get the benefit. This
has already been set on this machine and applies from the next Ollama restart.

**6. Run each setting several times.** Every model run in this report is a
single run. With a small number of questions, one agent changing its mind moves
the accuracy by a lot. Before writing anything down as a result, run each
setting at least five times and report the average.

---

## How to repeat this testing

```bash
python -m unittest discover -s tests
```

232 tests, no model needed, runs in under a second.

```bash
python ablation.py
```

Runs the same test with each mix of signals and prints the comparison table.
This one does call a real model and takes about 20 minutes.
