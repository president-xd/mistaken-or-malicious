"""The runtime loop that runs the peer network. This is NOT an orchestrator:
it does not answer, judge, or merge anything. It only (1) builds the topology,
(2) lets every peer answer on its own, then (3) repeatedly lets each peer hear
its topology-neighbours and decide for itself whether to change its mind.

Multiple questions are handled one by one: the same agents answer each question
in turn, and their memory is reset (via the SDK) between questions so every
question starts fresh.

Discussion is gossip-style: within a round, a later agent already sees the
updated answers of earlier agents. When a full round passes with nobody changing
their mind, the network is stable and we stop early.
"""

from __future__ import annotations

from . import logging_utils as log
from . import topology
from .agent import PeerAgent, agent_names, belief_shift, make_model_client
from .config import Config

# Belief mass a peer must gain before we call it a partial concession.
_CONCESSION = 0.05


def _gained_most(before: dict, after: dict, own: str) -> str:
    """Which rival answer this agent shifted the most weight onto."""
    rivals = {k: after.get(k, 0.0) - before.get(k, 0.0) for k in after if k != own}
    best = max(rivals, key=rivals.get, default="")
    return best if rivals.get(best, 0.0) > 0 else ""


async def run_network(cfg: Config) -> None:
    log.session(cfg)

    # Name the agents at runtime and wire them into the chosen topology once;
    # the same peers answer every question.
    names = agent_names(cfg.num_agents)
    adjacency = topology.build(cfg.topology, names)
    log.topology(cfg.topology, adjacency)

    client = make_model_client(cfg.model)
    agents = {name: PeerAgent(name, client) for name in names}

    try:
        for i, question in enumerate(cfg.questions, start=1):
            if i > 1:  # fresh start for each new question
                for agent in agents.values():
                    await agent.reset()
            log.question(i, len(cfg.questions), question)
            await _answer_one(cfg, agents, adjacency, names, question)
    finally:
        await client.close()


async def _answer_one(cfg, agents, adjacency, names, question) -> None:
    """Run the full independent + discussion cycle for a single question."""
    # Round 1 -- every peer answers alone (the independent guess).
    log.phase(f"ROUND 1/{cfg.rounds} - each agent answers independently")
    for name in names:
        log.thinking(name)
        text = await agents[name].solve(question)
        log.reply(name, text)
        if agents[name].retried:
            log.retry(name)
        if not agents[name].parsed:
            log.warn(name, "still no ANSWER line after retry - salvaged from the reply")
        log.held(name, agents[name].answer)

    # Rounds 2..N -- discussion: peers hear neighbours and may change their mind.
    for r in range(2, cfg.rounds + 1):
        log.phase(f"ROUND {r}/{cfg.rounds} - discussion")

        # SIMULTANEOUS UPDATE. Every agent's position is frozen here, before any
        # agent replies, and the whole round is served from this one snapshot.
        # So nobody can see an answer produced in the round they are taking part
        # in: there is no first mover, no stale reader, and information travels
        # exactly one hop per round no matter what order the turns happen in.
        # In "answer" mode a peer sends only its conclusion; in "both" mode it
        # also sends the reasoning, so peers debate arguments not assertions.
        snapshot = {
            m: (agents[m].answer,
                agents[m].argument() if cfg.share == "both" else "")
            for m in names
        }

        changes = 0
        moves = 0
        for name in names:
            agent = agents[name]
            neighbours = {m: snapshot[m] for m in adjacency[name]}
            log.hearing(name, neighbours)
            before = dict(agent.belief)
            text, did_change, convinced_by = await agent.reconsider(question, neighbours)
            log.reply(name, text)
            if agent.retried:
                log.retry(name)
            if not agent.parsed:
                log.warn(name, "still no ANSWER line after retry - previous answer kept, "
                               "change may be lost")
            if did_change:
                changes += 1
                log.changed(name, convinced_by)
            else:
                log.held(name, agent.answer)
            log.belief(name, agent.belief)

            # A PARTIAL concession: the agent kept its answer but moved real
            # belief mass toward a peer. Invisible in an answer-only system.
            shift = belief_shift(before, agent.belief)
            if before and not did_change and shift >= _CONCESSION:
                moves += 1
                log.conceded(name, shift, _gained_most(before, agent.belief, agent.answer))
        log.round_summary(r, changes, moves)
        if changes == 0 and moves == 0:
            log.info("No agent changed its mind - network is stable. Stopping early.")
            break

    # 3. Report this question's final state.
    log.final(agents)
