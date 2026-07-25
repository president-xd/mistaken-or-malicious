"""The run loop. Builds the network, runs the rounds, updates trust, scores it.

This file does NOT decide answers. Agents do that. This file only:
  1. works out who lies and where they sit
  2. wires the agents together using the topology
  3. gives every agent its turn
  4. updates the trust scores after each discussion round
  5. writes down what happened
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import replace

from . import logging_utils as log
from . import metrics, providers, repeat, roles, schedule, topology, trust as trust_math
from .agent import PeerAgent, agent_names, belief_shift, make_model_client
from .config import Config
from .embed import make_embedder

# How much belief must move before we call it a partial concession.
_CONCESSION = 0.05


def _gained_most(before: dict, after: dict, own: str) -> str:
    """Which rival answer this agent shifted the most weight onto."""
    rivals = {k: after.get(k, 0.0) - before.get(k, 0.0) for k in after if k != own}
    best = max(rivals, key=rivals.get, default="")
    return best if rivals.get(best, 0.0) > 0 else ""


class Network:
    """One network of agents, run over a list of questions."""

    def __init__(self, cfg: Config, client, force_trust=None, all_liars=False,
                 agents=None):
        """`agents` lets tests inject fake agents instead of real model-backed ones."""
        self.cfg = cfg
        self.names = list(agents) if agents else agent_names(cfg.agents)
        self.adjacency = topology.build(cfg.topology, self.names)
        self.use_trust = cfg.trust if force_trust is None else force_trust

        # Decide who lies. `all_liars` is used by the network-vs-network mode.
        if all_liars:
            self.liars = list(self.names)
        else:
            self.liars = roles.choose_seats(
                self.names, cfg.attackers, cfg.attacker_places,
                cfg.topology, cfg.seed)

        self.agents = agents or {
            name: PeerAgent(
                name, client,
                role="liar" if name in self.liars else "honest",
                wrong_answer=cfg.attacker_answer,
                agreeableness=cfg.trait_for(i, "agreeableness"),
                persuasion=cfg.trait_for(i, "persuasion"))
            for i, name in enumerate(self.names)
        }

        # trust[listener][speaker]. Only agents you can hear are ever scored.
        self.trust = {
            listener: {speaker: cfg.start_trust
                       for speaker in self.speakers_for(listener)}
            for listener in self.names
        }
        self.embedder = make_embedder(cfg.scoring, cfg.embed_model)
        self.previous_vectors: dict[str, list[float]] = {}
        self.rows: list[dict] = []
        # A copy of the trust table after each round, so we can judge
        # how FAST and how STEADY the formula is, not just the end value.
        self.history: list[dict] = []
        self.last_scores: dict[str, float] = {}
        # A sleeper behaves well for the first half of the questions, then lies.
        self.learning = True   # may this question change trust?
        self.asleep = cfg.sleeper
        self.wake_after = max(1, len(cfg.questions) // 2) if cfg.sleeper else 0

    # ------------------------------------------------------------- listening

    def speakers_for(self, listener: str) -> list[str]:
        """Everyone this agent keeps a trust score for: its neighbours, and
        itself when `hear_yourself` is on."""
        peers = list(self.adjacency[listener])
        if self.cfg.hear_yourself:
            peers.append(listener)
        return peers

    def heard_by(self, name: str) -> list[str]:
        """Who this agent can hear, after the trust floor removes distrusted peers."""
        peers = self.adjacency[name]
        if self.use_trust and self.cfg.trust_floor > 0:
            peers = [p for p in peers if self.trust[name][p] >= self.cfg.trust_floor]
        return peers

    def neighbours_of(self, name: str, snapshot: dict) -> dict:
        """What this agent is shown this round.

        With `hear_yourself` on, its own previous view is included as one of the
        sources, the same as any peer. That lets an agent weigh its own past
        opinion against the group instead of only against others.
        """
        heard = {m: snapshot[m] for m in self.heard_by(name)}
        if self.cfg.hear_yourself:
            heard[name] = snapshot[name]
        return heard

    async def _all(self, make_call):
        """Run one call per agent.

        With `parallel` on they all run together, which is roughly `agents`
        times faster. The result is identical either way, because every agent
        was already given the same frozen snapshot before any call started.
        """
        if self.cfg.parallel:
            return await asyncio.gather(*(make_call(n) for n in self.names))
        return [await make_call(n) for n in self.names]

    # ----------------------------------------------------------- trust maths

    def update_trust(self, learn=True):
        """Score every agent on this round, then move the trust values.

        Returns the signal table so it can be shown and saved.
        """
        cfg = self.cfg
        vectors = {n: self.embedder.vector(self.agents[n].answer) for n in self.names}
        if hasattr(self.embedder, "pad_all"):
            # With exact matching, a new answer adds a new slot, so vectors get
            # longer as the run goes on. Pad THIS round and the PREVIOUS round to
            # the same width. Without this, an agent that moves to a brand new
            # answer is compared on the old, shorter width, and looks unchanged.
            width = max([len(v) for v in vectors.values()]
                        + [len(v) for v in self.previous_vectors.values()] or [0])
            vectors = {n: v + [0.0] * (width - len(v)) for n, v in vectors.items()}
            self.previous_vectors = {n: v + [0.0] * (width - len(v))
                                     for n, v in self.previous_vectors.items()}

        # Work out the three signals for every agent.
        raw_agree, raw_anomaly, consist = {}, {}, {}
        for name in self.names:
            others = [vectors[m] for m in self.names if m != name]
            raw_agree[name] = trust_math.agree_score(vectors[name], others)
            raw_anomaly[name] = trust_math.anomaly_score(vectors[name], others)
            consist[name] = trust_math.consist_score(
                vectors[name], self.previous_vectors.get(name))

        # Exact matching only uses half the range (see trust.stretch_exact).
        if cfg.scoring == "answer":
            raw_agree = {n: trust_math.stretch_exact(v) for n, v in raw_agree.items()}
            consist = {n: trust_math.stretch_exact(v) for n, v in consist.items()}
            raw_anomaly = {n: trust_math.stretch_exact(v, is_anomaly=True)
                           for n, v in raw_anomaly.items()}

        # Real embeddings squash everything together, so optionally stretch the
        # range we actually saw. See trust.sharpen for why.
        agree = trust_math.sharpen(raw_agree) if cfg.sharpen else raw_agree
        anomaly = trust_math.sharpen(raw_anomaly) if cfg.sharpen else raw_anomaly

        signals = {}
        for name in self.names:
            score = trust_math.behaviour_score(
                agree[name], consist[name], anomaly[name],
                cfg.weight_agree, cfg.weight_consist, cfg.weight_anomaly)
            signals[name] = {
                "agree": round(agree[name], 4),
                "consist": round(consist[name], 4),
                "anomaly": round(anomaly[name], 4),
                "score": round(score, 4),
            }

        # Move every listener's trust in every speaker it can hear.
        # When `learn` is off, trust is frozen and only the signals are shown.
        for listener in (self.names if learn else []):
            for speaker in self.speakers_for(listener):
                self.trust[listener][speaker] = trust_math.update_trust(
                    self.trust[listener][speaker],
                    signals[speaker]["score"], cfg.trust_memory)

        self.previous_vectors = vectors
        self.last_scores = {n: signals[n]['score'] for n in signals}
        self.history.append({i: dict(r) for i, r in self.trust.items()})
        return signals

    def influence(self) -> dict:
        return {listener: trust_math.influence_shares(row)
                for listener, row in self.trust.items()}

    # ---------------------------------------------------------- the run loop

    async def run_question(self, question, recorder=None):
        """One question, start to finish. Returns its scores."""
        cfg = self.cfg
        log.question_header(question.text, question.answer)

        # Give every liar the wrong answer for THIS question. A single wrong
        # answer for the whole run would be nonsense once the topic changes.
        #
        # A sleeper is different: while it is still "asleep" it defends the
        # CORRECT answer. It looks like a good agent, earns high trust, and only
        # starts lying later. This is the hardest case for the defence, because
        # trust is built on past behaviour.

        # Remember the trust this question really starts from. The check that
        # compares the code with the maths needs it, and after a warm-up it is
        # NOT the `start_trust` setting any more.
        self.trust_at_start = {i: dict(r) for i, r in self.trust.items()}

        wrong = question.wrong or cfg.attacker_answer
        for name in self.liars:
            self.agents[name].wrong_answer = (
                question.answer if self.asleep else wrong)
        if self.asleep:
            log.info(f"{'sleeper' if len(self.liars) == 1 else 'sleepers'} still "
                     f"asleep - defending the CORRECT answer to build trust")

        # Round 1: everyone answers alone.
        log.phase(f"ROUND 1/{cfg.rounds} - each agent answers alone")
        log.working(self.names, cfg.parallel)
        texts = await self._all(lambda n: self.agents[n].solve(question.text))
        for name, text in zip(self.names, texts):
            log.reply(name, text)
            self._report(name)
        first_answers = {n: self.agents[n].answer for n in self.names}

        if recorder:
            recorder.add_round(1, self.agents)

        # Rounds 2..N: discussion, then a trust update.
        for r in range(2, cfg.rounds + 1):
            log.phase(f"ROUND {r}/{cfg.rounds} - discussion")
            snapshot = {
                m: (self.agents[m].answer,
                    self.agents[m].argument() if cfg.share == "both" else "")
                for m in self.names
            }
            # Work out what each agent hears BEFORE anyone replies, then let
            # them all reply at once. Nobody can see this round's new answers.
            hears = {n: self.neighbours_of(n, snapshot) for n in self.names}
            before = {n: dict(self.agents[n].belief) for n in self.names}
            for name in self.names:
                log.hearing(name, hears[name],
                            self.trust[name] if self.use_trust else None)

            log.working(self.names, cfg.parallel)
            # Hand each agent its own trust row, so it can weigh peers by it.
            replies = await self._all(
                lambda n: self.agents[n].reconsider(
                    question.text, hears[n],
                    self.trust[n] if self.use_trust else None))

            changes = 0
            for name, (text, changed, by) in zip(self.names, replies):
                log.reply(name, text)
                self._report(name, changed, by)
                shift = belief_shift(before[name], self.agents[name].belief)
                if before[name] and not changed and shift >= _CONCESSION:
                    log.conceded(name, shift,
                                 _gained_most(before[name], self.agents[name].belief,
                                              self.agents[name].answer))
                changes += changed

            # On a frozen question we still SHOW the signals but do not
            # move the trust values.
            signals = (self.update_trust(learn=self.learning)
                       if self.use_trust else None)
            if self.use_trust:
                log.trust_table(signals, self.trust, self.liars)
                log.influence_line(self.influence(), self.liars)
            log.round_summary(r, changes)
            if recorder:
                recorder.add_round(r, self.agents, self.trust if self.use_trust else None,
                                   signals, self.influence() if self.use_trust else None)

            # Stop early if nobody moved. We only do this when trust is OFF:
            # trust keeps changing after answers settle, and it needs the full
            # number of rounds to separate a liar from the honest agents.
            if changes == 0 and not self.use_trust:
                log.info("No agent changed its mind - network is stable. Stopping early.")
                break

        # Score it.
        final = {n: self.agents[n].answer for n in self.names}
        scores = metrics.summarise(first_answers, final, self.trust,
                                   self.liars, question.answer)
        if self.use_trust and self.history:
            scores.update(metrics.formula_report(
                self.history, self.last_scores, self.liars,
                cfg.trust_memory, self.trust_at_start))
        self.rows.append(scores)
        per_agent = metrics.per_agent(self.agents, self.trust, self.liars)
        log.final_report(self.agents, self.liars, question.answer, scores,
                         self.use_trust)
        if recorder:
            recorder.finish_question(final, scores, per_agent)
        return scores

    def _report(self, name, changed=False, by=""):
        """Print what happened on one agent's turn."""
        agent = self.agents[name]
        if agent.retried:
            log.retry(name)
        if not agent.parsed:
            log.warn(name, "no ANSWER line after retry - previous answer kept")
        if changed:
            log.changed(name, by)
        else:
            log.held(name, agent.answer, name in self.liars)
        log.belief(name, agent.belief)

    async def warm_up(self, questions):
        """Run a few questions just to see who is good, then set starting trust.

        We score each agent on its ROUND 1 answer only - what it knew before any
        discussion. That way an agent cannot earn trust simply by talking others
        round. Accuracy is raised to the power `trust_gamma`, which pushes weak
        agents further down: at gamma 2, an accuracy of 0.7 becomes 0.49.

        The warm-up questions are NOT scored afterwards.
        """
        cfg = self.cfg
        log.banner(f"WARM-UP - {len(questions)} question(s) used only to set starting trust")
        correct = {n: 0 for n in self.names}

        for i, question in enumerate(questions, start=1):
            if i > 1:
                await self.reset_agents()
            log.question_header(question.text, question.answer)
            wrong = question.wrong or cfg.attacker_answer
            for name in self.liars:
                # A sleeper defends the CORRECT answer during warm-up, so it
                # looks good and earns high trust before it starts lying.
                self.agents[name].wrong_answer = (
                    question.answer if cfg.sleeper else wrong)
            log.working(self.names, cfg.parallel)
            texts = await self._all(lambda n: self.agents[n].solve(question.text))
            for name, text in zip(self.names, texts):
                log.reply(name, text)
                self._report(name)
                if metrics.is_correct(self.agents[name].answer, question.answer):
                    correct[name] += 1

        # accuracy ** gamma, then everyone starts with that view of each speaker.
        log.banner("WARM-UP RESULT - starting trust")
        for name in self.names:
            score = (correct[name] / len(questions)) ** cfg.trust_gamma
            score = min(max(score, 0.0), 1.0)
            for listener in self.names:
                if name in self.trust[listener]:
                    self.trust[listener][name] = score
            log.info(f"  {name}: right {correct[name]}/{len(questions)} "
                     f"-> starting trust {score:.3f}"
                     + ("  [LIAR]" if name in self.liars else ""))
        await self.reset_agents()

    async def reset_agents(self):
        for agent in self.agents.values():
            await agent.reset()
        self.previous_vectors = {}
        self.history = []
        if not self.cfg.trust_carry_over:
            self.trust = {
                listener: {s: self.cfg.start_trust for s in self.adjacency[listener]}
                for listener in self.names
            }


# ------------------------------------------------------------------ entry

async def run_network(cfg: Config, recorder=None) -> None:
    """Run everything the config asks for."""
    # Fail now if the provider cannot work at all, rather than half a run in.
    providers.check_ready(cfg.provider)
    client = make_model_client(cfg.model, cfg.provider)
    try:
        if cfg.repeats > 1:
            await _repeat(cfg, client, recorder)
        else:
            random.seed(cfg.seed)
            await _once(cfg, client, recorder)
    finally:
        await client.close()


async def _once(cfg: Config, client, recorder):
    """Run the chosen experiment exactly once.

    Gives back the two summaries as (left, right). `left` is None for a plain
    run, because there is nothing to compare against. In a comparison, `left`
    is the setup we are testing against and `right` is the new one.
    """
    if cfg.compare_baseline:
        return await _compare(cfg, client, recorder)
    if cfg.network_vs_network:
        return await _network_vs_network(cfg, client, recorder)

    net = Network(cfg, client)
    log.session(cfg, net.names, net.liars, net.adjacency, net.use_trust)
    await _run_all(net, cfg, recorder)
    summary = metrics.average_runs(net.rows)
    if recorder:
        recorder.set_summary(summary)
    return None, summary


async def _repeat(cfg: Config, client, recorder):
    """Run the WHOLE experiment several times and report the average.

    Each repeat gets its own seed, so the liars sit in different seats and the
    model is asked afresh. One run of one setup is luck; the average over
    several runs, with the spread shown next to it, is a result.

    Inside one repeat both halves of a comparison share that repeat's seed, so
    they are still tested under exactly the same conditions as each other.
    """
    log.banner(f"REPEATING THE WHOLE EXPERIMENT {cfg.repeats} TIMES\n"
               f"One run is luck. The average over the repeats, and how far "
               f"apart they were, is the result.")
    lefts, rights = [], []

    for i in range(cfg.repeats):
        seed = cfg.seed + i
        this_run = replace(cfg, seed=seed)
        random.seed(seed)
        log.repeat_header(i + 1, cfg.repeats, seed)
        if recorder:
            recorder.start_repeat(i + 1, seed)
        left, right = await _once(this_run, client, recorder)
        if left is not None:
            lefts.append(left)
        rights.append(right)

    combined_right = repeat.combine(rights)
    if lefts:
        combined_left = repeat.combine(lefts)
        left_name = "honest network" if cfg.network_vs_network else "without trust"
        right_name = "all-liar network" if cfg.network_vs_network else "with trust"
        log.repeats_comparison(combined_left, combined_right, cfg.repeats,
                               left=left_name, right=right_name)
    else:
        log.repeats_table(combined_right, f"AVERAGE OVER {cfg.repeats} REPEATS")

    if recorder:
        # The averaged numbers replace the last repeat's numbers as the
        # headline, and every repeat is kept so nothing is lost.
        recorder.set_summary(repeat.means_only(combined_right))
        recorder.set_repeats(cfg.repeats, rights, combined_right,
                            lefts or None,
                            repeat.combine(lefts) if lefts else None)


async def _run_all(net, cfg, recorder):
    """Warm up if asked, then run and score the remaining questions."""
    questions = list(cfg.questions)

    # The warm-up questions are used only to set starting trust, then dropped.
    if cfg.warmup > 0:
        if net.use_trust:
            await net.warm_up(questions[:cfg.warmup])
        else:
            # The baseline has no trust to warm up, but it must still SKIP these
            # questions. Otherwise the two halves of a comparison would be
            # scored on different questions, and the comparison would be wrong.
            log.info(f"skipping the first {cfg.warmup} warm-up question(s) so "
                     f"both halves are scored on the same questions")
        questions = questions[cfg.warmup:]

    # Decide up front which questions trust may learn from.
    plan = schedule.build_plan(len(questions), cfg.trust_learn_on,
                               cfg.trust_learn_share, cfg.seed)
    if net.use_trust and cfg.trust_learn_on != "all":
        log.info(schedule.describe(plan, cfg.trust_learn_on))

    for i, question in enumerate(questions, start=1):
        if i > 1:
            await net.reset_agents()
        # A sleeper wakes up part-way through and starts lying.
        if net.asleep and i > net.wake_after:
            net.asleep = False
            log.banner("THE SLEEPER WAKES UP - it now defends a WRONG answer")
        net.learning = (plan[i - 1] == "learn")
        if recorder:
            recorder.start_question(question.text, question.answer)
        await net.run_question(question, recorder)


async def _compare(cfg, client, recorder):
    """Run the same test twice - trust off, then trust on - and compare."""
    log.banner("EXPERIMENT: baseline (no trust)  vs  dynamic trust")

    off = Network(cfg, client, force_trust=False)
    log.session(cfg, off.names, off.liars, off.adjacency, False)
    await _run_all(off, cfg, None)
    without = metrics.average_runs(off.rows)

    random.seed(cfg.seed)          # same seats, same conditions
    on = Network(cfg, client, force_trust=True)
    log.session(cfg, on.names, on.liars, on.adjacency, True)
    await _run_all(on, cfg, recorder)
    with_trust = metrics.average_runs(on.rows)

    log.comparison(without, with_trust)
    if recorder:
        recorder.set_summary(with_trust)
        recorder.set_comparison(without, with_trust)
    return without, with_trust


async def _network_vs_network(cfg, client, recorder):
    """An all-honest network against an all-liar network, on the same questions."""
    log.banner("EXPERIMENT: honest network  vs  all-liar network")

    honest = Network(cfg, client, all_liars=False)
    honest.liars = []
    for agent in honest.agents.values():
        agent.role = "honest"
    log.session(cfg, honest.names, [], honest.adjacency, honest.use_trust)
    await _run_all(honest, cfg, None)

    liars = Network(cfg, client, all_liars=True)
    log.session(cfg, liars.names, liars.liars, liars.adjacency, liars.use_trust)
    await _run_all(liars, cfg, recorder)

    good, bad = metrics.average_runs(honest.rows), metrics.average_runs(liars.rows)
    log.comparison(good, bad, left="honest network", right="all-liar network")
    if recorder:
        recorder.set_summary(bad)
    return good, bad
