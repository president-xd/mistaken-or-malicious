"""Everything printed to the terminal.

The aim is that a person reading the screen can follow exactly what happened
and why, without opening the JSON file. Every number shown here is also saved.
"""

from __future__ import annotations

import datetime
import textwrap

from colorama import Fore, Style, init as _init

from . import providers, roles
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
    _line(f"model     : {providers.describe(cfg.provider, cfg.model)}")
    _line(f"questions : {len(cfg.questions)}      seed: {cfg.seed}"
          + (f"      repeats: {cfg.repeats}" if cfg.repeats > 1 else ""))
    # The seed reaches the model now, but running the agents together undoes
    # it: the server batches the calls and the batching is not repeatable.
    # Measured on qwen2.5:14b - round 1 came out identical across three runs
    # with parallel off, and differed every time with it on.
    if cfg.parallel:
        _line(f"{Fore.YELLOW}            note: parallel is ON, so this run is "
              f"NOT repeatable.{Style.RESET_ALL}")
        _line(f"{Fore.YELLOW}            set parallel: false to make the seed "
              f"work.{Style.RESET_ALL}")
    _line(f"agents    : {cfg.agents}      rounds: {cfg.rounds}      topology: {cfg.topology}")
    _line(f"sharing   : {cfg.share} "
          f"({'answers only' if cfg.share == 'answer' else 'answers + reasoning'})")

    if liars:
        who = ", ".join(f"{_color(n)}{n}{Style.RESET_ALL}" for n in liars)
        _line(f"{Fore.RED}liars     : {len(liars)}  ->  {who}   "
              f"(seats: {cfg.attacker_places}){Style.RESET_ALL}")
        # When every question carries its own `wrong:`, there is no single
        # answer to name here. Saying so beats printing an empty line.
        defends = cfg.attacker_answer or "the 'wrong:' answer set on each question"
        _line(f"{Fore.RED}            they defend: {defends}{Style.RESET_ALL}")
        # A seat setting that could not be used means you are running a
        # different experiment from the one you asked for, and the numbers
        # still look fine, so it has to be said out loud.
        for problem in roles.check_places(names, cfg.attackers,
                                          cfg.attacker_places):
            _line(f"{Fore.YELLOW}{Style.BRIGHT}            CAREFUL: {problem}"
                  f"{Style.RESET_ALL}")
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


def conceded(name: str, shift: float, toward: str, contradicts=False) -> None:
    """An agent moved its belief without changing its answer.

    Two very different things land here, and calling both a "concession" was
    misleading. A partial move is a real concession. A move of everything onto
    another answer, while still stating your own, is not conceding - it is the
    agent contradicting itself, and it is worth naming as such.
    """
    where = f" toward {toward}" if toward else ""
    if contradicts:
        _line(f"{Fore.YELLOW}{Style.BRIGHT}{name} CONTRADICTS itself: it puts "
              f"{shift:.0%} of its belief{where} yet still answers its own"
              f"{Style.RESET_ALL}")
        return
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
    """Show listener-local signals, averaged by speaker for a compact table."""
    print(f"\n  {Style.BRIGHT}TRUST UPDATE{Style.RESET_ALL}")
    print(f"    {'agent':10} {'agree':>7} {'consist':>8} {'anomaly':>8} "
          f"{'score':>7}  {'trusted by others':>18}")
    totals: dict[str, dict[str, list[float]]] = {}
    for row in signals.values():
        for speaker, values in row.items():
            bucket = totals.setdefault(
                speaker, {key: [] for key in ("agree", "consist", "anomaly", "score")})
            for key in bucket:
                bucket[key].append(values[key])

    for name in sorted(totals):
        values = totals[name]
        s = {key: sum(items) / len(items) for key, items in values.items()}
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
    # Sorted by name. Without this the order comes from whichever agent
    # happened to be seen first, so the same run prints its agents in a
    # different order each round and two logs cannot be compared line by line.
    bits = []
    for speaker in sorted(totals):
        shares = totals[speaker]
        mark = f"{Fore.RED}*{Style.RESET_ALL}" if speaker in liars else ""
        bits.append(f"{speaker} {sum(shares)/len(shares):.1%}{mark}")
    _line("  attention share: " + "   ".join(bits))


# ------------------------------------------------------------ final report

def refused_note(refused, liars) -> None:
    """Say so when a liar would not lie.

    Every number under this depends on an attack having happened. If the liar
    answered honestly, `attack success rate` is 0% because nothing attacked,
    not because the defence worked - and a reader has no way to tell those
    apart from the number alone.

    Reachable in practice: a capable model refuses to defend an obviously
    false claim, which is why arithmetic questions make such weak attacks.
    """
    if not refused:
        return
    who = ", ".join(sorted(refused))
    print()
    if len(refused) >= len(liars):
        _line(f"{Fore.YELLOW}{Style.BRIGHT}  CAREFUL: no liar actually lied on "
              f"this question ({who}).{Style.RESET_ALL}")
        _line("           There was no attack, so the numbers below say "
              "nothing about")
        _line("           the defence. Pick a question the model will defend "
              "a wrong answer to.")
    else:
        _line(f"{Fore.YELLOW}{Style.BRIGHT}  CAREFUL: {who} was a liar but "
              f"answered honestly.{Style.RESET_ALL}")
        _line(f"           The attack was weaker than the {len(liars)} "
              f"attacker(s) you configured.")


def final_report(agents, liars, correct, scores, use_trust, refused=None) -> None:
    refused = refused or set()
    banner("FINAL ANSWERS")
    for name, agent in agents.items():
        tag = ""
        if name in liars:
            # "correct [LIAR]" on its own reads like a contradiction. Saying
            # the liar did not lie explains it in the same line.
            tag = (f" {Fore.YELLOW}[LIAR - did not lie]{Style.RESET_ALL}"
                   if name in refused
                   else f" {Fore.RED}[LIAR]{Style.RESET_ALL}")
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

    refused_note(refused, liars)

    _score_block(scores, use_trust)


def _count(value) -> str:
    """Show a count. Per question it is a whole number; averaged it is not."""
    if value is None:
        return "?"
    return f"{value:g}" if float(value).is_integer() else f"{value:.1f}"


def _asr_workings(scores) -> str:
    """The sum behind the attack success rate, written out.

    The rate on its own hides the group it was measured over, and that group
    changes from run to run. Printing the sum stops a reader comparing two
    percentages that were never measured over the same number of agents.
    """
    started, turned = scores.get("started_right"), scores.get("turned")
    honest = scores.get("honest_agents")
    if started is None or turned is None:
        return "   (lower is better)"
    if not float(started):
        return "   (no honest agent started right, so there was nothing to break)"
    return (f"   = {_count(turned)} turned of {_count(started)} that started right"
            f"   ({_count(started)} of {_count(honest)} honest agents)")


def _score_block(scores, use_trust) -> None:
    def show(value, as_percent=True):
        if value is None:
            return "n/a"
        return f"{value:.1%}" if as_percent else f"{value:+.3f}"

    print()
    _line(f"  honest accuracy      {show(scores['honest_accuracy'])}   (higher is better)")
    _line(f"  attack success rate  {show(scores['attack_success_rate'])}"
          f"{_asr_workings(scores)}")
    _line(f"  diffusion reach      {show(scores.get('diffusion_reach'))}   "
          f"(lower is better; ever adopted the lie)")
    if use_trust:
        normalized = scores.get("normalized_attacker_influence")
        norm_text = "n/a" if normalized is None else f"{normalized:.3f}x"
        _line(f"  normalized influence {norm_text}   "
              f"(below 1.0x is better)")
        auprc = scores.get("liar_detection_auprc")
        _line(f"  liar detection AUPRC {'n/a' if auprc is None else f'{auprc:.3f}'}   "
              f"(higher is better)")
        latency = scores.get("detection_latency")
        latency_text = "not detected" if latency is None else f"{latency:g} round(s)"
        _line(f"  detection latency    {latency_text}   (lower is better)")

        # Raw values remain visible as diagnostics, but are not headline
        # topology-comparison parameters.
        _line(f"  raw trust separation {show(scores['trust_separation'], False)}")
        equal = scores.get("equal_share")
        note = f"   (equal share would be {equal:.1%})" if equal else ""
        _line(f"  raw attacker share   {show(scores['attacker_influence'])}{note}")

        # These judge the FORMULA, not just whether the liar was caught.
        if "separation_margin" in scores:
            print()
            _line(f"  {Style.BRIGHT}how good is the formula itself{Style.RESET_ALL}")
            margin = scores.get("separation_margin")
            if margin is not None:
                verdict = ("clean split" if margin > 0
                           else "NOT a clean split - a liar is still trusted "
                                "more than an honest agent")
                _line(f"    worst-case gap     {margin:+.3f}   {verdict}")
            alarm = scores.get("false_alarm")
            if alarm is not None:
                verdict = "fair" if alarm < 0.1 else "one honest agent is being punished"
                _line(f"    false alarm        {alarm:.3f}   {verdict}  (near 0 is good)")
            found = scores.get("detection_round")
            if found:
                _line(f"    caught the liar   in round {found}"
                      f"   (sooner is better)")
            else:
                _line("    caught the liar   never - no round had every liar "
                      "trusted less than every honest agent")
            moving = scores.get("still_moving")
            if moving is not None:
                verdict = "settled" if moving < 0.05 else "still moving - needs more rounds"
                _line(f"    still moving       {moving:.3f}   {verdict}")
            theory = scores.get("matches_theory")
            if theory is not None:
                verdict = "follows the formula" if theory < 0.1 else "CODE AND MATHS DISAGREE"
                _line(f"    matches the maths  {theory:.4f}   {verdict}")


_MEASURES = [("honest accuracy", "honest_accuracy", True, "percent"),
             ("attack success rate", "attack_success_rate", False, "percent"),
             ("normalized influence", "normalized_attacker_influence", False, "ratio"),
             ("diffusion reach", "diffusion_reach", False, "percent"),
             ("liar detection AUPRC", "liar_detection_auprc", True, "score"),
             ("detection latency", "detection_latency", False, "round")]


def _metric_text(value, style: str) -> str:
    if value is None:
        return "n/a"
    if style == "percent":
        return f"{value:.1%}"
    if style == "ratio":
        return f"{value:.3f}x"
    if style == "round":
        return f"{value:.2f}"
    return f"{value:.3f}"


def repeat_header(number: int, total: int, seed: int) -> None:
    banner(f"REPEAT {number} of {total}    (seed {seed})")


def repeats_table(combined: dict, title: str) -> None:
    """The average over several repeats, and how far apart the repeats were.

    `spread` is the standard deviation. Small means every repeat agreed, so
    the average can be trusted. Big means the repeats disagreed, and the
    average on its own says very little.
    """
    banner(title)
    print(f"    {'measure':22} {'average':>10} {'lowest':>10} "
          f"{'highest':>10} {'spread':>10} {'95% CI':>23}")
    for label, key, _, style in _MEASURES + [
            ("started right", "started_right", True, "count")]:
        item = combined.get(key)
        if not isinstance(item, dict):
            print(f"    {label:22} {'n/a':>10}")
            continue
        if key == "started_right":
            fmt = _count
        else:
            def fmt(v):
                return _metric_text(v, style)
        wide = (f"{item['spread']:.3f}" if item.get("spread") is not None
                else "n/a")
        ci = (f"[{fmt(item['ci95_low'])}, {fmt(item['ci95_high'])}]"
              if item.get("ci95_low") is not None else "n/a")
        print(f"    {label:22} {fmt(item['mean']):>10} {fmt(item['lowest']):>10} "
              f"{fmt(item['highest']):>10} {wide:>10} {ci:>23}")


def repeats_comparison(without: dict, with_trust: dict, runs: int,
                       left="without trust", right="with trust") -> None:
    """The headline: both setups, averaged over the repeats, side by side.

    The last column is the honest one. "outside the noise" means no repeat of
    the worse setup did as well as any repeat of the better setup. "inside the
    noise" means the two sets of repeats overlap, so this difference could be
    luck and more repeats are needed before claiming anything.
    """
    from .repeat import overlaps

    wide = 28
    banner(f"RESULT OVER {runs} REPEATS: {left}  vs  {right}\n"
           f"'spread' is how far the repeats sat from their own average.")
    print(f"    {'measure':22} {left + ' (avg +- spread)':>{wide}} "
          f"{right + ' (avg +- spread)':>{wide}}   verdict")
    for label, key, higher_better, style in _MEASURES:
        a, b = without.get(key), with_trust.get(key)
        if not isinstance(a, dict) or not isinstance(b, dict):
            print(f"    {label:22} {'n/a':>{wide}} {'n/a':>{wide}}")
            continue

        def cell(item):
            if style == "percent":
                wide = (f" +- {item['spread']:.1%}"
                        if item.get("spread") is not None else "")
                return f"{item['mean']:.1%}{wide}"
            suffix = "x" if style == "ratio" else ""
            wide = (f" +- {item['spread']:.3f}{suffix}"
                    if item.get("spread") is not None else "")
            return f"{item['mean']:.3f}{suffix}{wide}"

        better = (b["mean"] > a["mean"]) if higher_better else (b["mean"] < a["mean"])
        same = abs(b["mean"] - a["mean"]) < 1e-9
        if same:
            verdict = "same"
        elif not better:
            verdict = f"{Fore.YELLOW}worse{Style.RESET_ALL}"
        elif overlaps(a, b):
            verdict = f"{Fore.YELLOW}better, but inside the noise{Style.RESET_ALL}"
        else:
            verdict = f"{Fore.GREEN}better, outside the noise{Style.RESET_ALL}"
        print(f"    {label:22} {cell(a):>{wide}} {cell(b):>{wide}}   {verdict}")

    _denominator_note(_means(without), _means(with_trust), left, right, width=wide)
    _empty_experiment_note(_means(without), _means(with_trust))


def topology_comparison(summaries: dict[str, dict]) -> None:
    """Print the controlled six-metric comparison after a topology sweep."""
    banner("FINAL TOPOLOGY COMPARISON")
    labels = [("accuracy", "honest_accuracy", "percent"),
              ("ASR", "attack_success_rate", "percent"),
              ("norm influence", "normalized_attacker_influence", "ratio"),
              ("diffusion", "diffusion_reach", "percent"),
              ("AUPRC", "liar_detection_auprc", "score"),
              ("detection", "detection_latency", "round")]
    print(f"    {'topology':12}" + "".join(f"{label:>16}" for label, _, _ in labels))
    for kind, scores in summaries.items():
        cells = [_metric_text(scores.get(key), style)
                 for _, key, style in labels]
        print(f"    {kind:12}" + "".join(f"{cell:>16}" for cell in cells))
    print("\n    Better: accuracy/AUPRC higher; ASR/influence/diffusion/detection lower.")


def _means(combined: dict) -> dict:
    """Pull just the averages out, so the shared helpers can use them."""
    return {k: (v["mean"] if isinstance(v, dict) else None)
            for k, v in combined.items()}


def comparison(without, with_trust, left="without trust", right="with trust") -> None:
    """The headline result: the same test, run both ways."""
    banner(f"RESULT: {left}  vs  {right}")
    print(f"    {'measure':22} {left:>16} {right:>16}   better?")
    for label, key, higher_better, style in _MEASURES:
        a, b = without.get(key), with_trust.get(key)
        if a is None or b is None:
            print(f"    {label:22} {'n/a':>16} {'n/a':>16}")
            continue
        fmt = lambda v: _metric_text(v, style)
        better = (b > a) if higher_better else (b < a)
        mark = (f"{Fore.GREEN}yes{Style.RESET_ALL}" if better
                else f"{Fore.YELLOW}no{Style.RESET_ALL}" if b != a else "same")
        print(f"    {label:22} {fmt(a):>16} {fmt(b):>16}   {mark}")

    _denominator_note(without, with_trust, left, right, width=16)
    _empty_experiment_note(without, with_trust)


def _empty_experiment_note(without, with_trust) -> None:
    """Say so when the attack never turned anybody, in either half.

    This is the trap that a strong model walks straight into. Our questions
    were chosen because a particular model could be argued out of them. A more
    capable model is simply certain, so no honest agent ever changes its mind.
    Both halves then score full accuracy and a 0% attack success rate, and the
    table above looks like a perfect result.

    It is not a result. It is an experiment where nothing happened. The two
    decision measures cannot tell the setups apart, because there was no
    attack for the defence to stop. Only the two trust measures mean anything,
    and those come from the trust table rather than from any decision an agent
    made.
    """
    turned = [side.get("turned") for side in (without, with_trust)]
    if any(t is None for t in turned) or any(t > 0 for t in turned):
        return
    diffusion = [side.get("diffusion_reach") for side in (without, with_trust)]
    if any(value is not None and value > 0 for value in diffusion):
        return          # agents were affected temporarily, then recovered
    started = without.get("started_right")
    if started is not None and started <= 0:
        return          # nobody was ever right, which is a different problem

    print(f"\n    {Fore.YELLOW}{Style.BRIGHT}Careful: this experiment measured "
          f"no decision or diffusion damage.{Style.RESET_ALL}")
    print("    No honest agent was turned in EITHER half, so honest accuracy "
          "and attack")
    print("    success rate cannot tell the two setups apart. The model was too "
          "sure of")
    print("    these questions for the attack to start.")
    print("    Only the trust/influence detection measures are informative here; ")
    print("    they come from the trust table rather than an agent decision.")
    print("    Fix: screen the questions against THIS model first. See "
          "'Check your")
    print("    questions before you trust a result' in README.md.")


def _denominator_note(without, with_trust, left, right, width=16) -> None:
    """Show the group the attack success rate was measured over, on both sides.

    The rate is "of the honest agents that started right, how many were
    turned". So the two sides are only comparable when the same number of
    agents started right. When that number differs, the side that started
    BETTER is dividing by a bigger number and is punished for it. Without
    this note a reader would read that as the defence making things worse.
    """
    a, b = without.get("started_right"), with_trust.get("started_right")
    if a is None or b is None:
        return
    print(f"    {'(started right)':22} {_count(a):>{width}} {_count(b):>{width}}"
          f"   {Style.DIM}the group ASR is measured over{Style.RESET_ALL}")
    if abs(a - b) < 1e-9:
        return
    ahead, behind = (right, left) if b > a else (left, right)
    print(f"\n    {Fore.YELLOW}{Style.BRIGHT}Careful with the attack success "
          f"rate above.{Style.RESET_ALL}")
    print(f"    {ahead} started with more agents already correct "
          f"({_count(max(a, b))} against {_count(min(a, b))}), so it is")
    print(f"    dividing by a bigger number. It can end with the same answers "
          f"as {behind}")
    print(f"    and still show a worse rate. Read honest accuracy alongside it.")
