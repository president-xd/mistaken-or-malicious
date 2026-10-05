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
from .agent import (PeerAgent, agent_names, belief_shift, make_clients,
                    make_model_client, top_answer)
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
        self.show_trust = self.use_trust and cfg.trust_share != "off"

        # Decide who lies. `all_liars` is used by the network-vs-network mode.
        if all_liars:
            self.liars = list(self.names)
        else:
            self.liars = roles.choose_seats(
                self.names, cfg.attackers, cfg.attacker_places,
                cfg.topology, cfg.seed)
        if ((cfg.attacker_places or "").strip().lower() == "strategic"
                and len(self.liars) != min(cfg.attackers, len(self.names))):
            raise RuntimeError(
                f"strategic placement requested {cfg.attackers} liar(s) but "
                f"selected {len(self.liars)}; refusing to run a different experiment")

        # `client` may be one shared client, or a list holding one per agent so
        # each can carry its own seed. See agent.make_clients.
        def client_for(index):
            if isinstance(client, (list, tuple)):
                return client[index % len(client)]
            return client

        self.agents = agents or {
            name: PeerAgent(
                name, client_for(i),
                role="liar" if name in self.liars else "honest",
                wrong_answer=cfg.attacker_answer,
                agreeableness=cfg.trait_for_role(
                    i, "liar" if name in self.liars else "honest", "agreeableness"),
                persuasion=cfg.trait_for_role(
                    i, "liar" if name in self.liars else "honest", "persuasion"))
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
        # Liars that answered something other than the lie they were given.
        # An empty set means every liar really attacked.
        self.liar_refused: set[str] = set()
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
        if self.show_trust and self.cfg.trust_floor > 0:
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

        # Work out the signals separately for every listener/speaker edge.
        # A listener may use its own answer and the answers of peers it can
        # actually hear, but never a remote agent hidden by the topology. The
        # old implementation compared every speaker with the entire network,
        # which let a distant honest majority rescue sparse topologies.
        raw: dict[str, dict[str, dict[str, float]]] = {}
        for listener in self.names:
            speakers = self.speakers_for(listener)
            locally_visible = list(dict.fromkeys([listener, *speakers]))
            raw[listener] = {}
            for speaker in speakers:
                others = [vectors[name] for name in locally_visible
                          if name != speaker]
                raw[listener][speaker] = {
                    "agree": trust_math.agree_score(vectors[speaker], others),
                    "consist": trust_math.consist_score(
                        vectors[speaker], self.previous_vectors.get(speaker)),
                    "anomaly": trust_math.anomaly_score(vectors[speaker], others),
                }

        # Exact matching only uses half the range (see trust.stretch_exact).
        if cfg.scoring == "answer":
            for row in raw.values():
                for speaker, values in row.items():
                    values["agree"] = trust_math.stretch_exact(values["agree"])
                    values["anomaly"] = trust_math.stretch_exact(
                        values["anomaly"], is_anomaly=True)
                    # No previous answer means neutral, not a failed consistency
                    # check. Stretch only real similarity measurements.
                    values["consist"] = (
                        trust_math.stretch_exact(values["consist"])
                        if speaker in self.previous_vectors
                        else trust_math.NEUTRAL)

        # Embedding similarities can occupy a very narrow range. Sharpen only
        # within one listener's local evidence; global sharpening would leak
        # remote agents back into the calculation.
        signals: dict[str, dict[str, dict[str, float]]] = {}
        for listener, row in raw.items():
            raw_agree = {speaker: values["agree"]
                         for speaker, values in row.items()}
            raw_anomaly = {speaker: values["anomaly"]
                           for speaker, values in row.items()}
            agree = trust_math.sharpen(raw_agree) if cfg.sharpen else raw_agree
            anomaly = (trust_math.sharpen(raw_anomaly)
                       if cfg.sharpen else raw_anomaly)
            signals[listener] = {}
            for speaker, values in row.items():
                score = trust_math.behaviour_score(
                    agree[speaker], values["consist"], anomaly[speaker],
                    cfg.weight_agree, cfg.weight_consist, cfg.weight_anomaly)
                signals[listener][speaker] = {
                    "agree": round(agree[speaker], 4),
                    "consist": round(values["consist"], 4),
                    "anomaly": round(anomaly[speaker], 4),
                    "score": round(score, 4),
                    "exact": score,
                }

        # Move every listener's trust in every speaker it can hear.
        # When `learn` is off, trust is frozen and only the signals are shown.
        for listener in (self.names if learn else []):
            for speaker in self.speakers_for(listener):
                self.trust[listener][speaker] = trust_math.update_trust(
                    self.trust[listener][speaker],
                    signals[listener][speaker]["exact"], cfg.trust_memory)

        self.previous_vectors = vectors
        self.last_scores = {
            listener: {speaker: values["exact"]
                       for speaker, values in row.items()}
            for listener, row in signals.items()
        }
        self.history.append({i: dict(r) for i, r in self.trust.items()})
        return signals

    def heard_trust(self) -> dict:
        """The trust table cut down to who each listener ACTUALLY hears.

        `trust_floor` stops an agent listening to a peer it distrusts. That
        peer is then silent as far as this listener is concerned, so its share
        of the attention is zero - not the share its trust value suggests.

        Without this the influence numbers counted peers that had already been
        shut out. Measured with trust_floor 0.45: Agent_A heard only Agent_C,
        yet the liar Agent_B was still credited with 38.8% of A's attention.
        Since influence is one of the headline measures, the
        defence looked worse than it actually was.

        With `trust_floor` at its default of 0 nothing is filtered and this
        returns the full table, so ordinary runs are unaffected.
        """
        out = {}
        for listener, row in self.trust.items():
            heard = set(self.heard_by(listener))
            if self.cfg.hear_yourself:
                heard.add(listener)
            out[listener] = {s: v for s, v in row.items() if s in heard}
        return out

    def influence(self) -> dict:
        return {listener: trust_math.influence_shares(row)
                for listener, row in self.heard_trust().items()}

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

        # Cleared per question. Refusing to lie on one question says nothing
        # about the next, and without this a single refusal early on would
        # mark the liar as broken for the whole run.
        self.liar_refused = set()

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
        round_answers = [dict(first_answers)]

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
                            self.trust[name] if self.show_trust else None)

            log.working(self.names, cfg.parallel)
            # Hand each agent its own trust row, so it can weigh peers by it.
            replies = await self._all(
                lambda n: self.agents[n].reconsider(
                    question.text, hears[n],
                    self.trust[n] if self.show_trust else None))

            changes = 0
            for name, (text, changed, by) in zip(self.names, replies):
                log.reply(name, text)
                self._report(name, changed, by)
                shift = belief_shift(before[name], self.agents[name].belief)
                if before[name] and not changed and shift >= _CONCESSION:
                    log.conceded(
                        name, shift,
                        _gained_most(before[name], self.agents[name].belief,
                                     self.agents[name].answer),
                        # A full move onto another answer is not a concession,
                        # it is the agent disagreeing with itself.
                        contradicts=getattr(self.agents[name],
                                            "belief_disagrees", False))
                changes += changed

            round_answers.append({n: self.agents[n].answer for n in self.names})

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


        # Score it.
        final = {n: self.agents[n].answer for n in self.names}
        # The metrics see only what each listener actually hears, so a peer
        # silenced by `trust_floor` no longer counts toward its influence.
        # With the floor at 0 this is the whole table, as before.
        heard = self.heard_trust()
        scores = metrics.summarise(
            first_answers, final, heard, self.liars, question.answer,
            round_answers=round_answers, wrong=wrong,
            detection_trust=self.trust)
        if self.use_trust and self.history:
            scores.update(metrics.formula_report(
                self.history, self.last_scores, self.liars,
                cfg.trust_memory, self.trust_at_start))
        self.rows.append(scores)
        per_agent = metrics.per_agent(self.agents, heard, self.liars)
        log.final_report(self.agents, self.liars, question.answer, scores,
                         self.use_trust, self.liar_refused)
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

        # The three checks below read optional attributes with getattr, so any
        # stand-in agent object works without having to declare them.

        # A liar that answered something other than the lie it was handed has
        # refused to attack. Without this the run still calls it [LIAR] and
        # scores the experiment as though an attack happened, when it did not.
        #
        # Skipped while a sleeper is still asleep. During that phase the liar
        # is deliberately given the CORRECT answer to defend, so it is not
        # meant to be attacking and saying "it is NOT attacking" would be
        # reporting the intended behaviour as a problem.
        lie = getattr(agent, "wrong_answer", "")
        if name in self.liars and lie and agent.answer and not self.asleep:
            if not metrics.is_correct(agent.answer, lie):
                # Say it once per question, not once per round. The same
                # sentence three times in a row is noise, and noise is what
                # stops people reading warnings at all.
                if name not in self.liar_refused:
                    log.warn(name, f"was told to answer {lie!r} but answered "
                                   f"{agent.answer!r} - it is NOT attacking")
                self.liar_refused.add(name)
            else:
                # It went back to attacking, so let it be reported again if it
                # stops later in the same question.
                self.liar_refused.discard(name)

        # The BELIEF line was unusable, so the confidence shown below is our
        # fallback, not the model's opinion. This used to be silent.
        if getattr(agent, "belief_ignored", False):
            log.warn(name, "its BELIEF line named no real answer - the "
                           "confidence below is a fallback, not its own view")
        # The agent's own belief contradicts the answer it gave.
        if getattr(agent, "belief_disagrees", False):
            log.warn(name, f"answered {agent.answer!r} but puts most of its "
                           f"belief on {top_answer(agent.belief)!r}")

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
    client = None
    try:
        if cfg.topologies:
            client = make_clients(cfg.model, cfg.provider, cfg.seed, cfg.agents)
            await _topology_sweep(cfg, client, recorder)
        elif cfg.repeats > 1:
            await _repeat(cfg, recorder)
        else:
            client = make_clients(cfg.model, cfg.provider, cfg.seed, cfg.agents)
            random.seed(cfg.seed)
            # Only this branch may checkpoint and resume. A sweep or a set of
            # repeats writes many runs into one recorder, so "how far did we
            # get" is not a single number and a half-restored file would mix
            # two experiments together.
            await _once(cfg, client, recorder, resumable=True)
    finally:
        # One client per agent now, so close them all.
        if client is not None:
            for one in (client if isinstance(client, (list, tuple)) else [client]):
                await one.close()


async def _topology_sweep(cfg: Config, client, recorder=None):
    """Run one controlled experiment per topology, then compare the six metrics."""
    from .results import Results

    summaries = {}
    for kind in cfg.topologies:
        log.banner(f"TOPOLOGY SWEEP: {kind.upper()}")
        this_cfg = replace(cfg, topology=kind, topologies=[])
        names = agent_names(this_cfg.agents)
        liars = roles.choose_seats(names, this_cfg.attackers,
                                   this_cfg.attacker_places, kind,
                                   this_cfg.seed)
        child = Results(this_cfg, names, liars) if recorder else None
        random.seed(this_cfg.seed)
        if this_cfg.repeats > 1:
            _, summary = await _repeat(this_cfg, child)
        else:
            _, summary = await _once(this_cfg, client, child)
        summaries[kind] = summary
        if recorder:
            recorder.add_topology(kind, child)

    log.topology_comparison(summaries)
    return summaries


async def _once(cfg: Config, client, recorder, resumable=False):
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
    failed = await _run_all(net, cfg, recorder, resumable)
    summary = metrics.average_runs(net.rows)
    if recorder:
        recorder.set_summary(summary)
        if resumable:
            recorder.mark_complete(failed)
    return None, summary


async def _repeat(cfg: Config, recorder):
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
        clients = make_clients(cfg.model, cfg.provider, seed, cfg.agents)
        random.seed(seed)
        log.repeat_header(i + 1, cfg.repeats, seed)
        if recorder:
            recorder.start_repeat(i + 1, seed)
        try:
            left, right = await _once(this_run, clients, recorder)
        finally:
            for client in clients:
                await client.close()
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
    return (repeat.means_only(combined_left) if lefts else None,
            repeat.means_only(combined_right))


def _restore(net, cfg, recorder):
    """Carry on from an unfinished run of this name. Returns (done, failed).

    Returns (0, []) when there is nothing to resume, which is the normal case.
    """
    from .results import load_checkpoint

    data = load_checkpoint(cfg.run_name, cfg.results_dir)
    if not data:
        return 0, []

    # Refuse to put two different experiments in one file. Resuming into a
    # checkpoint written under other settings would produce a result matching
    # neither config, and nothing in the file would say so afterwards.
    saved = data.get("settings", {})
    current = recorder.data.get("settings", {})
    changed = sorted(k for k in set(saved) | set(current)
                     if saved.get(k) != current.get(k))
    if changed:
        raise SystemExit(
            f"\nThere is an unfinished run called {cfg.run_name!r}, but it was "
            f"started with different settings:\n"
            f"  {', '.join(changed)}\n"
            f"Resuming would mix two experiments in one file. Give this run a "
            f"new `run_name`, or delete results/{cfg.run_name}.json to start "
            f"it again from the beginning.")

    progress = data.get("progress", {})
    done = int(progress.get("questions_done") or 0)
    if done <= 0:
        return 0, []

    recorder.adopt(data)
    # Trust and the scored rows are the run's memory. Without both, a resumed
    # run would start trusting everyone again and would report its summary
    # over only the questions asked after the restart.
    saved_trust = progress.get("trust")
    if saved_trust:
        net.trust = {a: dict(row) for a, row in saved_trust.items()}
    saved_rows = progress.get("rows")
    if saved_rows:
        net.rows = list(saved_rows)
    failed = list(progress.get("failed_questions", []))

    log.banner(f"RESUMING: {cfg.run_name}\n"
               f"{done} question(s) already answered - carrying on from "
               f"question {done + 1}.\n"
               f"Trust and scores are restored, so this stays one experiment.")
    return done, failed


def _is_permanent(exc) -> bool:
    """Is this an error that every later question would hit too?

    A timeout or a rate limit is bad luck and the next question may well be
    fine. A rejected key or an empty account is not: retrying it 100 times
    turns one clear failure into a hundred silent ones, and hides the single
    sentence the user actually needs to read.
    """
    status = getattr(exc, "status_code", None)
    if status in (401, 402, 403):
        return True
    text = str(exc).lower()
    return any(k in text for k in (
        "insufficient balance", "unauthorized", "invalid api key",
        "authentication", "error code: 401", "error code: 402",
        "error code: 403"))


async def _question_with_retry(net, cfg, question, recorder) -> bool:
    """Run one question, giving it a second chance. True if it finished.

    A single timed-out call used to end the whole experiment. The results file
    is written as the run goes now, but that only helps if one bad minute
    stops costing every question that came after it, so a failure here is
    retried once and then recorded as missing rather than raised.
    """
    last = None
    for attempt in (1, 2):
        if recorder:
            recorder.start_question(question.text, question.answer)
        try:
            await net.run_question(question, recorder)
            return True
        except (KeyboardInterrupt, asyncio.CancelledError):
            raise                      # the user asked to stop; let it stop
        except Exception as exc:       # noqa: BLE001 - no provider error ends the run
            last = exc
            if recorder:
                recorder.discard_question()
            # A dead key or an empty account will reject every remaining
            # question in exactly the same way. Stop now so the caller can say
            # so plainly; the questions already finished stay checkpointed.
            if _is_permanent(exc):
                log.warn("run", "the provider rejected this outright - stopping "
                                "rather than failing every remaining question")
                raise
            if attempt == 1:
                log.warn("question", f"failed ({type(exc).__name__}: {exc}) "
                                     f"- trying it once more")
                await net.reset_agents()

    log.warn("question", f"failed twice - recorded as missing, moving on: {last}")
    if recorder:
        recorder.record_failed_question(question.text, question.answer, last)
    return False


async def _run_all(net, cfg, recorder, resumable=False):
    """Warm up if asked, then run and score the remaining questions.

    Returns the list of question numbers that could not be completed.
    """
    questions = list(cfg.questions)

    # Work out where to start BEFORE the warm-up, because a resumed run must
    # not pay for the warm-up twice.
    done, failed = 0, []
    if resumable and recorder:
        done, failed = _restore(net, cfg, recorder)

    # The warm-up questions are used only to set starting trust, then dropped.
    if cfg.warmup > 0:
        if done > 0:
            # The warm-up exists only to set starting trust, and the restored
            # trust table already holds its effect. Running it again would
            # spend the calls and then be overwritten by the restore.
            log.info("resuming: skipping the warm-up, its trust is already restored")
        elif net.use_trust:
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
        if i <= done:
            continue                   # already answered before the interruption
        if i > 1:
            await net.reset_agents()
        # A sleeper wakes up part-way through and starts lying.
        if net.asleep and i > net.wake_after:
            net.asleep = False
            log.banner("THE SLEEPER WAKES UP - it now defends a WRONG answer")
        net.learning = (plan[i - 1] == "learn")

        if not await _question_with_retry(net, cfg, question, recorder):
            failed.append(i)

        # Save after every question. The file used to be written once, at the
        # very end, so anything that went wrong on question 87 threw away the
        # 86 questions already paid for.
        done = i
        if resumable and recorder:
            recorder.mark_progress(done, net.trust, net.rows, failed)
            recorder.checkpoint(folder=cfg.results_dir, run_name=cfg.run_name)

    if failed:
        log.warn("run", f"{len(failed)} question(s) could not be completed: "
                        f"{', '.join(str(n) for n in failed)}. They are marked "
                        f"'failed' in the results file and are not scored.")
    return failed


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
