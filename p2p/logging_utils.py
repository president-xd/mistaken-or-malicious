"""Everything printed to the terminal.

The aim is that a person reading the screen can follow exactly what happened
and why, without opening the JSON file. Every number shown here is also saved.
"""

from __future__ import annotations

import datetime
import textwrap

from colorama import Fore, Style, init as _init

from .agent import _norm
from .trust import half_life

_init()

_PALETTE = [Fore.CYAN, Fore.GREEN, Fore.YELLOW, Fore.MAGENTA, Fore.BLUE, Fore.RED]
_colors: dict[str, str] = {}


def _color(name: str) -> str:
    if name not in _colors:
        _colors[name] = _PALETTE[len(_colors) % len(_PALETTE)]
    return _colors[name]


def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _line(msg: str) -> None:
    print(f"{Style.DIM}{_ts()}{Style.RESET_ALL} {msg}")


def banner(text: str) -> None:
    bar = "=" * 74
    print(f"\n{Style.BRIGHT}{bar}\n{text}\n{bar}{Style.RESET_ALL}")


def phase(text: str) -> None:
    banner(text)


def info(msg: str) -> None:
    _line(msg)


# ------------------------------------------------------------ run header

def session(cfg, names, liars, adjacency, use_trust) -> None:
    banner("P2P AGENT NETWORK")
    _line(f"questions : {len(cfg.questions)}      model: {cfg.model}      seed: {cfg.seed}")
    _line(f"agents    : {cfg.agents}      rounds: {cfg.rounds}      topology: {cfg.topology}")
    _line(f"sharing   : {cfg.share} "
          f"({'answers only' if cfg.share == 'answer' else 'answers + reasoning'})")

    if liars:
        who = ", ".join(f"{_color(n)}{n}{Style.RESET_ALL}" for n in liars)
        _line(f"{Fore.RED}liars     : {len(liars)}  ->  {who}   "
              f"(seats: {cfg.attacker_places}){Style.RESET_ALL}")
        _line(f"{Fore.RED}            they defend: {cfg.attacker_answer}{Style.RESET_ALL}")
    else:
        _line("liars     : none - every agent is honest")

    if use_trust:
        _line(f"{Fore.GREEN}trust     : ON   scoring by {cfg.scoring}   "
              f"memory {cfg.trust_memory}{Style.RESET_ALL}")
        _line(f"            weights  agree {cfg.weight_agree:.3f}  "
              f"consist {cfg.weight_consist:.3f}  anomaly {cfg.weight_anomaly:.3f}")
        _line(f"            half-life {half_life(cfg.trust_memory):.1f} rounds"
              + ("   (carried over between questions)" if cfg.trust_carry_over else ""))
    else:
        _line("trust     : OFF - every agent is heard equally (baseline)")

    banner(f"TOPOLOGY: {cfg.topology}  (who can hear whom)")
    for node, peers in adjacency.items():
        _line(f"{_color(node)}{node}{Style.RESET_ALL} --> {', '.join(peers) or '(nobody)'}")


def question_header(text: str, correct: str) -> None:
    extra = f"   (correct answer: {correct})" if correct else ""
    banner(f"QUESTION: {text}{extra}")


# ------------------------------------------------------------ per agent

def thinking(name: str) -> None:
    _line(f"{_color(name)}{name}{Style.RESET_ALL} is thinking...")


def working(names, parallel: bool) -> None:
    """Say who is thinking, and whether they are doing it together."""
    how = "all at the same time" if parallel else "one after another"
    _line(f"{len(names)} agents thinking ({how})...")


def hearing(name: str, peers, trust_row=None) -> None:
    """Who this agent hears, the value it got, and how much it trusts them."""
    if not peers:
        _line(f"{_color(name)}{name}{Style.RESET_ALL} listens to: nobody")
        return
    bits = []
    for peer, (answer, _) in peers.items():
        if trust_row and peer in trust_row:
            bits.append(f"{peer}={answer} (trust {trust_row[peer]:.2f})")
        else:
            bits.append(f"{peer}={answer}")
    _line(f"{_color(name)}{name}{Style.RESET_ALL} listens to: {'  '.join(bits)}")


def reply(name: str, text: str) -> None:
    c = _color(name)
    print(f"{c}{Style.BRIGHT}{name} says:{Style.RESET_ALL}")
    for para in text.splitlines():
        if para.strip():
            print(textwrap.fill(para, width=88, initial_indent="    ",
                                subsequent_indent="    "))


def held(name: str, answer: str, is_liar: bool = False) -> None:
    tag = f" {Fore.RED}[LIAR]{Style.RESET_ALL}" if is_liar else ""
    _line(f"{_color(name)}{name} held its answer -> {answer}{Style.RESET_ALL}{tag}")


def changed(name: str, convinced_by: str) -> None:
    who = f"convinced by {convinced_by}" if convinced_by else "on its own reconsideration"
    _line(f"{Fore.RED}{Style.BRIGHT}{name} CHANGED its mind - {who}{Style.RESET_ALL}")


def belief(name: str, dist: dict) -> None:
    if not dist or len(dist) < 2:
        return
    parts = " ".join(f"{a}={p:.0%}" for a, p in
                     sorted(dist.items(), key=lambda kv: -kv[1]) if p > 0.005)
    _line(f"{_color(name)}{name}{Style.RESET_ALL} belief: {parts}")


def conceded(name: str, shift: float, toward: str) -> None:
    where = f" toward {toward}" if toward else ""
    _line(f"{Fore.MAGENTA}{Style.BRIGHT}{name} shifted {shift:.0%} of its belief"
          f"{where} - but kept its answer{Style.RESET_ALL}")


def retry(name: str) -> None:
    _line(f"{Fore.YELLOW}{name}: no ANSWER line - re-asking once...{Style.RESET_ALL}")


def warn(name: str, msg: str) -> None:
    _line(f"{Fore.YELLOW}{Style.BRIGHT}WARN {name}: {msg}{Style.RESET_ALL}")


def round_summary(r: int, changes: int) -> None:
    _line(f"round {r} complete: {Style.BRIGHT}{changes}{Style.RESET_ALL} "
          f"agent(s) changed their mind")


# ------------------------------------------------------------ trust output

def trust_table(signals: dict, trust: dict, liars: list) -> None:
    """Show the three signals and the resulting trust, so the maths is visible."""
    print(f"\n  {Style.BRIGHT}TRUST UPDATE{Style.RESET_ALL}")
    print(f"    {'agent':10} {'agree':>7} {'consist':>8} {'anomaly':>8} "
          f"{'score':>7}  {'trusted by others':>18}")
    for name, s in signals.items():
        got = [row[name] for row in trust.values() if name in row]
        average = sum(got) / len(got) if got else 0.0
        tag = f" {Fore.RED}[LIAR]{Style.RESET_ALL}" if name in liars else ""
        print(f"    {_color(name)}{name:10}{Style.RESET_ALL} {s['agree']:7.3f} "
              f"{s['consist']:8.3f} {s['anomaly']:8.3f} {s['score']:7.3f}  "
              f"{average:18.3f}{tag}")


def influence_line(influence: dict, liars: list) -> None:
    """How much of the talking each agent gets. This is communication strength."""
    if not influence:
        return
    totals: dict[str, list[float]] = {}
    for row in influence.values():
        for speaker, share in row.items():
            totals.setdefault(speaker, []).append(share)
    bits = []
    for speaker, shares in totals.items():
        mark = f"{Fore.RED}*{Style.RESET_ALL}" if speaker in liars else ""
        bits.append(f"{speaker} {sum(shares)/len(shares):.1%}{mark}")
    _line("  attention share: " + "   ".join(bits))


# ------------------------------------------------------------ final report

def final_report(agents, liars, correct, scores, use_trust) -> None:
    banner("FINAL ANSWERS")
    for name, agent in agents.items():
        tag = f" {Fore.RED}[LIAR]{Style.RESET_ALL}" if name in liars else ""
        right = ""
        if correct:
            right = (f" {Fore.GREEN}correct{Style.RESET_ALL}"
                     if _norm(agent.answer) == _norm(correct)
                     else f" {Fore.YELLOW}wrong{Style.RESET_ALL}")
        _line(f"{_color(name)}{name}{Style.RESET_ALL}: {agent.answer}{right}{tag}")

    unique = {_norm(a.answer) for a in agents.values()}
    if len(unique) == 1:
        _line(f"{Fore.GREEN}{Style.BRIGHT}CONSENSUS reached.{Style.RESET_ALL}")
    else:
        _line(f"{Fore.YELLOW}No full consensus: {len(unique)} distinct answers.{Style.RESET_ALL}")

    _score_block(scores, use_trust)


def _score_block(scores, use_trust) -> None:
    def show(value, as_percent=True):
        if value is None:
            return "n/a"
        return f"{value:.1%}" if as_percent else f"{value:+.3f}"

    print()
    _line(f"  honest accuracy      {show(scores['honest_accuracy'])}   (higher is better)")
    _line(f"  attack success rate  {show(scores['attack_success_rate'])}   (lower is better)")
    if use_trust:
        _line(f"  trust separation     {show(scores['trust_separation'], False)}   "
              f"(higher is better)")
        equal = scores.get("equal_share")
        note = f"   (equal share would be {equal:.1%})" if equal else ""
        _line(f"  attacker influence   {show(scores['attacker_influence'])}{note}")


def comparison(without, with_trust, left="without trust", right="with trust") -> None:
    """The headline result: the same test, run both ways."""
    banner(f"RESULT: {left}  vs  {right}")
    rows = [("honest accuracy", "honest_accuracy", True, True),
            ("attack success rate", "attack_success_rate", False, True),
            ("trust separation", "trust_separation", True, False),
            ("attacker influence", "attacker_influence", False, True)]
    print(f"    {'measure':22} {left:>16} {right:>16}   better?")
    for label, key, higher_better, as_percent in rows:
        a, b = without.get(key), with_trust.get(key)
        if a is None or b is None:
            print(f"    {label:22} {'n/a':>16} {'n/a':>16}")
            continue
        fmt = (lambda v: f"{v:.1%}") if as_percent else (lambda v: f"{v:+.3f}")
        better = (b > a) if higher_better else (b < a)
        mark = (f"{Fore.GREEN}yes{Style.RESET_ALL}" if better
                else f"{Fore.YELLOW}no{Style.RESET_ALL}" if b != a else "same")
        print(f"    {label:22} {fmt(a):>16} {fmt(b):>16}   {mark}")
