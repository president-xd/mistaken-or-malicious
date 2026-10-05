"""Read config.yaml and check it makes sense.

Every setting the user can change lives here. Nothing is hidden in the code.
If a setting is missing from the file, the default below is used, and the
default always keeps the old behaviour (no liars, no trust).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import providers, topology
from .schedule import LEARN_MODES

SHARE_MODES = ("answer", "both")
SCORING_MODES = ("answer", "text")
TRAIT_LEVELS = ("", "high", "medium", "low")


@dataclass
class Question:
    """One question, its correct answer, and the wrong answer a liar defends.

    `wrong` is per question on purpose. A single wrong answer for the whole run
    makes no sense: "347" is a believable wrong answer for 17 * 24, but nonsense
    for "what is the capital of Japan".
    """
    text: str
    answer: str = ""
    wrong: str = ""


@dataclass
class Config:
    # --- questions ---
    questions: list[Question] = field(default_factory=list)

    # --- model ---
    # Where the model runs: "ollama" on your own machine, or "deepseek" over
    # the API. The default stays local, so nothing costs money by accident.
    provider: str = "ollama"
    model: str = "llama3.2:1b"
    # The embedding model is only used by scoring: "text", and it always runs
    # locally on Ollama, whichever provider answers the questions.
    embed_model: str = "nomic-embed-text"

    # --- network ---
    agents: int = 3
    rounds: int = 2
    topology: str = "mesh"
    topologies: list[str] = field(default_factory=list)
    share: str = "answer"
    seed: int = 1

    # --- liars ---
    attackers: int = 0
    attacker_places: str = "random"
    attacker_answer: str = ""
    sleeper: bool = False

    # --- dynamic trust ---
    trust: bool = False
    scoring: str = "answer"
    start_trust: float = 0.5
    trust_memory: float = 0.8
    weight_agree: float = 1 / 3
    weight_consist: float = 1 / 3
    weight_anomaly: float = 1 / 3
    trust_floor: float = 0.0
    trust_carry_over: bool = True
    sharpen: bool = True
    trust_share: str = "broadcast"
    share_alpha: float = 0.5
    share_trim: int = 1
    attacker_reports: str = "truthful"

    # --- warm-up and learning schedule ---
    warmup: int = 0
    trust_gamma: float = 2.0
    trust_learn_on: str = "all"
    trust_learn_share: float = 0.5
    hear_yourself: bool = False

    # --- traits (optional, off by default) ---
    agreeableness: str = ""
    persuasion: str = ""
    honest_agreeableness: str = "high"
    liar_persuasion: str = "high"

    # --- running ---
    parallel: bool = True
    run_name: str = ""
    results_dir: str = "results"
    skip_done: bool = False
    # How many times to run the WHOLE experiment. Each repeat uses a different
    # seed, and the result is the average plus how far apart the repeats were.
    # 1 means a single run, which is fine for trying things out but is not
    # enough to report as a finding.
    repeats: int = 1

    # --- experiment modes ---
    compare_baseline: bool = False
    network_vs_network: bool = False

    def trait_for(self, index: int, which: str) -> str:
        """The trait level for agent number `index`, or "" if none was set."""
        text = self.agreeableness if which == "agreeableness" else self.persuasion
        levels = [p.strip().lower() for p in text.split(",") if p.strip()]
        return levels[index] if index < len(levels) else ""

    def trait_for_role(self, index: int, role: str, which: str) -> str:
        legacy = self.trait_for(index, which)
        if legacy:
            return legacy
        if role == "honest" and which == "agreeableness":
            return self.honest_agreeableness
        if role == "liar" and which == "persuasion":
            return self.liar_persuasion
        return ""


def _read_questions(raw) -> list[Question]:
    """Accept several shapes so old config files keep working.

    New style:  questions: [{text: "...", answer: "..."}]
    Old style:  questions: ["...", "..."]   or   question: "..."
    """
    items = raw.get("questions", raw.get("question"))
    if isinstance(items, (str, dict)):
        items = [items]
    out = []
    for item in items or []:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
            answer = str(item.get("answer", "")).strip()
            wrong = str(item.get("wrong", "")).strip()
        else:
            text, answer, wrong = str(item).strip(), "", ""
        if text:
            out.append(Question(text, answer, wrong))
    return out


def _read_questions_file(path: str) -> list[Question]:
    """Load questions from a separate file, so you can run many of them.

    Two formats are accepted:
      .yaml / .yml   a list of {text, answer, wrong}
      .jsonl         one JSON object per line, same keys
    """
    file = Path(path)
    if not file.exists():
        raise SystemExit(f"config error: questions file not found: {path}")
    text = file.read_text(encoding="utf-8")

    if file.suffix.lower() in (".yaml", ".yml"):
        items = yaml.safe_load(text) or []
    else:
        items = [json.loads(line) for line in text.splitlines() if line.strip()]

    out = [Question(str(i.get("text", "")).strip(),
                    str(i.get("answer", "")).strip(),
                    str(i.get("wrong", "")).strip())
           for i in items if isinstance(i, dict) and i.get("text")]
    if not out:
        raise SystemExit(f"config error: no questions found in {path}")
    return out


def load_config(path: str, share: str | None = None,
                provider: str | None = None, model: str | None = None) -> Config:
    """Read the config file. The three arguments are command line overrides.

    When you switch provider on the command line the old model name is usually
    wrong for the new provider, so if you give `--provider` without `--model`
    we fall back to that provider's default model rather than sending an
    ollama model name to the API.
    """
    # A missing or broken config file is the most common mistake of all, so it
    # gets a plain message instead of a traceback.
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise SystemExit(f"config file not found: {path}\n"
                         f"Check the path, or copy config.yaml to start from.")
    except (IsADirectoryError, PermissionError):
        # Windows raises PermissionError where Linux raises IsADirectoryError,
        # so both land here. A genuine permissions problem gets the same
        # message, which still points at the right thing to check.
        if Path(path).is_dir():
            raise SystemExit(f"'{path}' is a folder, not a config file.")
        raise SystemExit(f"cannot read '{path}' - check the file permissions.")
    except yaml.YAMLError as error:
        raise SystemExit(f"config file {path} is not valid YAML:\n  {error}")

    if not isinstance(raw, dict):
        raise SystemExit(f"config file {path} must be a set of settings like "
                         f"'agents: 4', not a {type(raw).__name__}.")

    from_file = str(raw.get("provider", "ollama")).lower()
    chosen = str(provider or from_file).lower()

    if model:
        chosen_model = model
    elif chosen != from_file:
        # The provider was switched on the command line and no model was named.
        # The model in the file belongs to the OTHER provider, so using it would
        # send an ollama model name to the API. Use this provider's default.
        chosen_model = providers.DEFAULT_MODEL.get(chosen, "")
    else:
        chosen_model = str(raw.get("model", "llama3.2:1b"))

    # Questions come either from a file or straight from this config.
    if raw.get("questions_file"):
        questions = _read_questions_file(str(raw["questions_file"]))
    else:
        questions = _read_questions(raw)
    if not questions:
        raise SystemExit(f"config error: no questions found in {path}")

    # Optionally use only the first few, so a big file can be tried quickly.
    limit = int(raw.get("max_questions", 0))
    if limit > 0:
        questions = questions[:limit]

    raw_topologies = raw.get("topologies", [])
    if raw_topologies is None:
        raw_topologies = []
    if not isinstance(raw_topologies, list):
        raise SystemExit(
            f"config error in {path}: 'topologies' must be a YAML list, "
            "for example: [mesh, star, ring]")
    topologies = [str(kind).strip().lower() for kind in raw_topologies]

    cfg = Config(
        questions=questions,
        provider=chosen,
        model=chosen_model,
        embed_model=str(raw.get("embed_model", "nomic-embed-text")),
        # "agents" is the new name; "num_agents" still works.
        agents=int(raw.get("agents", raw.get("num_agents", 3))),
        rounds=int(raw.get("rounds", 2)),
        topology=str(raw.get("topology", "mesh")).lower(),
        topologies=topologies,
        share=str(share or raw.get("share", "answer")).lower(),
        seed=int(raw.get("seed", 1)),
        attackers=int(raw.get("attackers", 0)),
        attacker_places=str(raw.get("attacker_places", "random")),
        attacker_answer=str(raw.get("attacker_answer", "")),
        sleeper=bool(raw.get("sleeper", False)),
        trust=bool(raw.get("trust", False)),
        scoring=str(raw.get("scoring", "answer")).lower(),
        start_trust=float(raw.get("start_trust", 0.5)),
        trust_memory=float(raw.get("trust_memory", 0.8)),
        weight_agree=float(raw.get("weight_agree", 1 / 3)),
        weight_consist=float(raw.get("weight_consist", 1 / 3)),
        weight_anomaly=float(raw.get("weight_anomaly", 1 / 3)),
        trust_floor=float(raw.get("trust_floor", 0.0)),
        trust_carry_over=bool(raw.get("trust_carry_over", True)),
        sharpen=bool(raw.get("sharpen", True)),
        trust_share=str(raw.get("trust_share", "broadcast")).lower(),
        share_alpha=float(raw.get("share_alpha", 0.5)),
        share_trim=int(raw.get("share_trim", 1)),
        attacker_reports=str(raw.get("attacker_reports", "truthful")).lower(),
        warmup=int(raw.get("warmup", 0)),
        trust_gamma=float(raw.get("trust_gamma", 2.0)),
        trust_learn_on=str(raw.get("trust_learn_on", "all")).lower(),
        trust_learn_share=float(raw.get("trust_learn_share", 0.5)),
        hear_yourself=bool(raw.get("hear_yourself", False)),
        agreeableness=str(raw.get("agreeableness", "")),
        persuasion=str(raw.get("persuasion", "")),
        honest_agreeableness=str(raw.get("honest_agreeableness", "high")),
        liar_persuasion=str(raw.get("liar_persuasion", "high")),
        parallel=bool(raw.get("parallel", True)),
        run_name=str(raw.get("run_name", "")),
        results_dir=str(raw.get("results_dir", "results")),
        skip_done=bool(raw.get("skip_done", False)),
        repeats=int(raw.get("repeats", 1)),
        compare_baseline=bool(raw.get("compare_baseline", False)),
        network_vs_network=bool(raw.get("network_vs_network", False)),
    )
    _check(cfg, path)
    return cfg


def _check(cfg: Config, path: str) -> None:
    """Catch mistakes before we spend time calling a model."""
    def stop(msg):
        raise SystemExit(f"config error in {path}: {msg}")

    if cfg.agents < 2:
        stop("'agents' must be at least 2 - one agent has nobody to talk to.")
    if cfg.rounds < 1:
        stop("'rounds' must be at least 1.")
    if cfg.repeats < 1:
        stop("'repeats' must be at least 1.")
    if cfg.share not in SHARE_MODES:
        stop(f"'share' must be one of: {', '.join(SHARE_MODES)}")
    if cfg.trust_share not in ("off", "broadcast"):
        stop("'trust_share' must be 'off' or 'broadcast'.")
    if not 0 <= cfg.share_alpha <= 1:
        stop("'share_alpha' must be between 0 and 1.")
    if cfg.share_trim < 0:
        stop("'share_trim' cannot be negative.")
    if cfg.attacker_reports not in ("truthful", "bad_mouth"):
        stop("'attacker_reports' must be 'truthful' or 'bad_mouth'.")
    if cfg.provider not in providers.PROVIDERS:
        stop(f"'provider' must be one of: {', '.join(providers.PROVIDERS)}")
    if not cfg.model:
        stop("'model' is empty. Name the model to use.")
    if cfg.scoring not in SCORING_MODES:
        stop(f"'scoring' must be one of: {', '.join(SCORING_MODES)}")
    if cfg.topology not in topology.available():
        stop(f"unknown topology '{cfg.topology}'. "
             f"choose one of: {', '.join(topology.available())}")
    for kind in cfg.topologies:
        if kind not in topology.available():
            stop(f"unknown topology '{kind}' in 'topologies'. "
                 f"choose from: {', '.join(topology.available())}")

    if not 0 <= cfg.attackers <= cfg.agents:
        stop(f"'attackers' must be between 0 and {cfg.agents}.")
    if cfg.attackers:
        # Each question needs a wrong answer for the liar to defend. It can be
        # set per question with 'wrong:', or once for all with 'attacker_answer'.
        for q in cfg.questions:
            if not q.wrong and not cfg.attacker_answer:
                stop(f"question '{q.text[:40]}...' has no wrong answer for the "
                     f"liar. Add 'wrong: <a believable wrong answer>' under the "
                     f"question, or set 'attacker_answer' for all of them.")
    if cfg.sleeper and not cfg.attackers:
        stop("'sleeper: true' needs at least one attacker.")

    # These two rules come straight from the formula. If either is broken the
    # maths stops working, so we refuse to run.
    total = cfg.weight_agree + cfg.weight_consist + cfg.weight_anomaly
    if total <= 0:
        stop("the three weights cannot all be zero.")
    if abs(total - 1.0) > 0.01:
        stop(f"weight_agree + weight_consist + weight_anomaly must add up to 1, "
             f"but they add up to {total:.3f}. Otherwise trust can leave the "
             f"0 to 1 range.")
    # Writing 0.333 three times gives 0.999, which is clearly what the user
    # meant. Scale the three so they add up to exactly 1.
    cfg.weight_agree /= total
    cfg.weight_consist /= total
    cfg.weight_anomaly /= total
    if not 0 <= cfg.trust_memory < 1:
        stop("'trust_memory' must be from 0 up to (but not including) 1. "
             "At exactly 1 trust would never change.")
    if not 0 <= cfg.start_trust <= 1:
        stop("'start_trust' must be between 0 and 1.")

    if cfg.trust_learn_on not in LEARN_MODES:
        stop(f"'trust_learn_on' must be one of: {', '.join(LEARN_MODES)}")
    if not 0 <= cfg.trust_learn_share <= 1:
        stop("'trust_learn_share' must be between 0 and 1.")
    if cfg.warmup < 0:
        stop("'warmup' cannot be negative.")
    if cfg.warmup >= len(cfg.questions):
        stop(f"'warmup' is {cfg.warmup} but there are only {len(cfg.questions)} "
             f"questions. Warm-up questions are not scored, so at least one "
             f"question must be left over.")

    for which in ("agreeableness", "persuasion"):
        text = getattr(cfg, which)
        for level in [p.strip().lower() for p in text.split(",") if p.strip()]:
            if level not in TRAIT_LEVELS:
                stop(f"'{which}' has an unknown level '{level}'. "
                     f"Use: high, medium, low")

    # A question with no answer cannot be scored. Warn rather than stop, so
    # plain discussion runs still work.
    if cfg.attackers or cfg.trust:
        missing = [q.text[:40] for q in cfg.questions if not q.answer]
        if missing:
            stop("every question needs an 'answer:' when using attackers or "
                 f"trust. Missing for: {missing[0]}...")
