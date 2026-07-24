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
from .agent import PeerAgent, agent_names, make_model_client
from .config import Config


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
        if not agents[name].parsed:
            log.warn(name, "no ANSWER line - fell back to the last line of the reply")
        log.held(name, agents[name].answer)

    # Rounds 2..N -- discussion: peers hear neighbours and may change their mind.
    for r in range(2, cfg.rounds + 1):
        log.phase(f"ROUND {r}/{cfg.rounds} - discussion")
        changes = 0
        for name in names:
            # In "answer" mode a peer sends only its conclusion; in "both" mode
            # it also sends the reasoning behind it, so peers debate arguments
            # instead of bare assertions.
            neighbours = {
                m: (agents[m].answer,
                    agents[m].argument() if cfg.share == "both" else "")
                for m in adjacency[name]
            }
            log.hearing(name, list(neighbours))
            text, did_change, convinced_by = await agents[name].reconsider(question, neighbours)
            log.reply(name, text)
            if not agents[name].parsed:
                log.warn(name, "no ANSWER line - previous answer kept, change may be lost")
            if did_change:
                changes += 1
                log.changed(name, convinced_by)
            else:
                log.held(name, agents[name].answer)
        log.round_summary(r, changes)
        if changes == 0:
            log.info("No agent changed its mind - network is stable. Stopping early.")
            break

    # 3. Report this question's final state.
    log.final(agents)
