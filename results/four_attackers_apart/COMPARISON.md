# Four attackers, maximally spaced on a seven-agent ring

Both arms completed on 2026-10-14. They use the same 50-question set, seven
agents, five discussion rounds, 40% seeded honest-error rate, and three
repeats. Attackers are Agents A, C, E, and G (seats 0, 2, 4, and 6); the three
remaining agents are honest. Four attackers cannot all be nonadjacent on a
seven-node ring, so this is a maximally spaced arrangement with one adjacent
wraparound pair, G–A. The defense-off and defense-on processes ran concurrently,
and agent calls were parallel within each arm.

| Measure | Defense off | Defense on | Change (on − off) |
|---|---:|---:|---:|
| Honest accuracy before discussion | 57.33% | 57.33% | 0.00 pp |
| Honest accuracy after five rounds | 55.33% | 58.89% | +3.56 pp |
| Attack success rate | 42.97% | 39.00% | −3.97 pp |
| Diffusion reach | 22.83% | 20.89% | −1.94 pp |
| Honest agents converted per question (mean) | 1.260 | 1.140 | −0.120 |
| Normalized attacker influence | 1.092× | 1.071× | −0.022× |
| Trust separation (honest minus attacker trust) | −0.206 | −0.212 | −0.006 |
| Liar-detection AUPRC | 0.468 | 0.469 | +0.001 |

Ranges across the three repeats were: final honest accuracy 55.33% off and
55.33%–63.33% on; attack success 42.52%–43.54% off and 34.01%–43.54% on;
diffusion reach 20.65%–25.00% off and 17.39%–23.55% on. AUPRC was 0.466–0.471
off and 0.467–0.473 on.

Attack success is the share of eligible honest agents who finish with an
attacker's designated wrong answer. Diffusion reach is the share of initially
correct honest agents who adopted that answer at any point during discussion,
including agents who later recovered. Normalized attacker influence compares
the attacker's attention share to an equal-share baseline; values above 1.0
mean attackers receive more than an equal share. Trust separation is average
trust in honest agents minus average trust in attackers, so negative values
mean the attackers are trusted more.

## Interpretation

The four-attacker defense-off arm shows stronger attack impact than the
three-attacker defense-off arm: final honest accuracy fell from 71.50% to
55.33%, attack success rose from 26.87% to 42.97%, and diffusion reach rose
from 14.35% to 22.83%.

Defense modestly improved final accuracy by 3.56 percentage points and reduced
attack success by 3.97 points and diffusion reach by 1.94 points. However, the
effects were not consistent across all paired repeats: in repeat 1 attack
success was unchanged and diffusion reach increased. Attacker influence also
remained above the equal-share baseline with defense on (1.071×), trust
separation stayed negative, and AUPRC remained around 0.47—below the 4/7
attacker-prevalence baseline of about 0.57. This indicates the trust signal did
not reliably identify the attackers in this majority-attacker setup, despite
the modest average improvement in answer outcomes. Treat the estimates as
descriptive; there are three repeats.

## Files

- Defense off: `defence_off/four_attackers_apart_defence_off.json`
- Defense on: `defence_on/four_attackers_apart_defence_on.json`
- Trust logs and console logs are stored beside each JSON.
- Matching configs: `../../configs/ring/four_attackers_apart/`
