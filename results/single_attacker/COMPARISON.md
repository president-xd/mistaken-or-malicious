# One-attacker comparison

Completed on 2026-10-14. Both arms use the same seven-agent ring, 50 questions,
five discussion rounds, one attacker at seat 0, and three repeats. The defense
arm enables trust-based defense; the baseline disables it. Each arm's JSON file
contains the question-level transcripts and per-repeat metrics.

| Measure | Defense off | Defense on | Change (on − off) |
|---|---:|---:|---:|
| Honest accuracy before discussion | 60.33% | 60.03% | −0.30 pp |
| Honest accuracy after five rounds | 95.11% | 96.06% | +0.95 pp |
| Attack success rate | 4.69% | 3.33% | −1.36 pp |
| Diffusion reach | 2.12% | 0.00% | −2.12 pp |
| Converted honest agents per question (mean) | 0.200 | 0.115 | −0.085 |
| Normalized attacker influence | 0.375 | 0.311 | −0.065 |

Attack success is the share of eligible honest agents who finish with the
attacker's answer. Diffusion reach counts initially-correct honest agents who
adopted the lie at any point in the discussion, including agents who later
recovered. `Normalized attacker influence` compares the attacker's share of
attention with its equal-share baseline; below 1.0 means it received less than
an equal share.

## Interpretation

Defense reduced the already-small spread: diffusion reach was nonzero in all
three defense-off repeats (0.92%–3.23%) and zero in all three defense-on
repeats. The attack success rate also fell, though the repeat ranges overlap
(3.67%–5.33% off; 2.33%–4.40% on). Final honest accuracy increased by only
0.95 percentage points, from an already-high 95.11%.

This one-attacker setup therefore does not show a large attack impact or a
large accuracy gap. It is a completed baseline for comparing the planned
two-, three-, and four-attacker runs; it should not be presented as evidence
of a large defense effect. There are three repeats, so treat the differences
as descriptive results for this setup.

## Files

- Defense off: `defence_off/single_attacker_defence_off.json`
- Defense on: `defence_on/single_attacker_defence_on.json`
- Configs: `../../configs/ring/single_attacker/defence_off.yaml` and
  `../../configs/ring/single_attacker/defence_on.yaml`
