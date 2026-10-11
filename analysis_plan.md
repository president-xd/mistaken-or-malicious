# Ring-only mistaken-vs-malicious analysis plan

The network has seven seats (`Agent_A` through `Agent_G`) in a ring, with only
the `honest` and `liar` roles. Each question runs for five rounds: solo
answers in round 1 and four discussion rounds. `warmup: 0` is fixed.

## Arms

S0 is the clean, no-attacker arm. S1-S5 use the explicit seats in
`configs/ring_scenarios.yaml`. Every attack scenario is run with defence OFF
(shadow trust is still computed and logged, with equal-share influence) and
defence ON. The same screened questions and seeds are paired across arms.

## Metrics and uncertainty

Per-question results include honest start/end accuracy, attack success,
diffusion reach, normalized attacker influence, liar AUPRC, and detection
latency. Honest-wrong questions are labelled only after the run: compare their
final trust with liar trust, calculate restricted AUPRC, split corrected versus
stayed-wrong, and report the clean-arm false-alarm rate. Recovery Rate is
`(A_defended - A_attacked) / (A_clean - A_attacked)` and is reported only when
the denominator is at least 0.10; otherwise it is **gap too small**.

Headline values use paired bootstrap 95% confidence intervals over questions.
No ground truth is sent into the network or trust formula; correctness is used
only by post-hoc analysis.

## Question selection gate

Question selection uses **only solo screening**, with three samples per
candidate and no attackers or discussion. Questions correct in one or two
samples are retained, and the most frequent wrong letter is recorded. If
fewer than 60 intermediate questions remain, screening stops with an explicit
error. Attack outcomes are never used for selection.
