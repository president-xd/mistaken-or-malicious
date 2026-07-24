"""Verbose, colorized terminal logging -- the project's "window" into the run.

Every meaningful event is printed with a timestamp and a per-agent color so you
can watch the network think, hear its peers, and change its mind in real time.
"""

from __future__ import annotations

import datetime
import textwrap

from colorama import Fore, Style, init as _init

from .agent import _norm

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


# -- structural output --------------------------------------------------------

def banner(text: str) -> None:
    bar = "=" * 74
    print(f"\n{Style.BRIGHT}{bar}\n{text}\n{bar}{Style.RESET_ALL}")


def session(cfg) -> None:
    banner("P2P AGENT NETWORK")
    _line(f"questions: {Style.BRIGHT}{len(cfg.questions)}{Style.RESET_ALL} to answer, one by one")
    _line(f"sdk      : autogen-agentchat  |  model: {cfg.model}")
    _line(f"agents   : {cfg.num_agents}   |  rounds: {cfg.rounds}   |  topology: {cfg.topology}")
    what = "answers only" if cfg.share == "answer" else "answers + reasoning"
    _line(f"sharing  : {cfg.share}  ({what} sent to neighbours)")


def question(i: int, total: int, text: str) -> None:
    banner(f"QUESTION {i}/{total}: {text}")


def topology(kind: str, adjacency: dict[str, list[str]]) -> None:
    banner(f"TOPOLOGY: {kind}  (who can hear whom)")
    for node, peers in adjacency.items():
        c = _color(node)
        heard = ", ".join(peers) if peers else "(isolated)"
        _line(f"{c}{node}{Style.RESET_ALL} --> {heard}")


def phase(text: str) -> None:
    banner(text)


# -- per-agent output ---------------------------------------------------------

def thinking(name: str) -> None:
    _line(f"{_color(name)}{name}{Style.RESET_ALL} is thinking...")


def hearing(name: str, peers: list[str]) -> None:
    who = ", ".join(peers) if peers else "no one"
    _line(f"{_color(name)}{name}{Style.RESET_ALL} listens to: {who}")


def reply(name: str, text: str) -> None:
    """Print the agent's full reasoning, indented under its name."""
    c = _color(name)
    print(f"{c}{Style.BRIGHT}{name} says:{Style.RESET_ALL}")
    for para in text.splitlines():
        if para.strip():
            print(textwrap.fill(para, width=88, initial_indent="    ",
                                subsequent_indent="    "))


def changed(name: str, convinced_by: str) -> None:
    """Printed only when an agent truly changes its answer, naming who convinced it."""
    who = f"convinced by {convinced_by}" if convinced_by else "on its own reconsideration"
    _line(f"{Fore.RED}{Style.BRIGHT}{name} CHANGED its mind - {who}{Style.RESET_ALL}")


def held(name: str, answer: str) -> None:
    _line(f"{_color(name)}{name} held its answer -> {answer}{Style.RESET_ALL}")


def round_summary(r: int, changes: int) -> None:
    _line(f"round {r} complete: {Style.BRIGHT}{changes}{Style.RESET_ALL} agent(s) changed their mind")


def info(msg: str) -> None:
    _line(msg)


def warn(name: str, msg: str) -> None:
    """A parse problem worth seeing -- never fail silently."""
    _line(f"{Fore.YELLOW}{Style.BRIGHT}WARN {name}: {msg}{Style.RESET_ALL}")


# -- final report -------------------------------------------------------------

def final(agents: dict) -> None:
    banner("FINAL ANSWERS")
    for name, a in agents.items():
        _line(f"{_color(name)}{name}{Style.RESET_ALL}: {a.answer}")
    # Same normalization the change-detector uses, so the two always agree.
    unique = {_norm(a.answer) for a in agents.values()}
    if len(unique) == 1:
        _line(f"{Fore.GREEN}{Style.BRIGHT}CONSENSUS reached.{Style.RESET_ALL}")
    else:
        _line(f"{Fore.YELLOW}No full consensus: {len(unique)} distinct answers remain.{Style.RESET_ALL}")
