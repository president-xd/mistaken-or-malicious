"""Is the three-signal formula actually needed?

This runs the same test several times, each time using a different mix of the
three signals, and prints the results side by side.

Why this matters: a formula that catches the liar is not automatically a good
formula. If one signal on its own does the same job, the other two are just
extra complexity. And if a very simple rule does the same job, the whole formula
is hard to justify.

Run:  python ablation.py
"""

import json
import os
import subprocess
import sys
import tempfile

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))

# question, correct answer, believable wrong answer
QUESTIONS = [
    {"text": "Which planet is closest to the Sun?", "answer": "Mercury", "wrong": "Venus"},
]

BASE = {
    "model": "llama3.1:8b-instruct-q8_0",
    "embed_model": "nomic-embed-text",
    "agents": 3, "rounds": 3, "topology": "mesh", "seed": 1,
    "questions": QUESTIONS,
    "attackers": 1, "attacker_places": "2",
    "trust": True, "scoring": "answer", "parallel": True,
}

# name -> (weight on agree, weight on consist, weight on anomaly)
MIXES = {
    "all three (1/3 each)": (1 / 3, 1 / 3, 1 / 3),
    "agree only":           (1.0, 0.0, 0.0),
    "consist only":         (0.0, 1.0, 0.0),
    "anomaly only":         (0.0, 0.0, 1.0),
    "agree + anomaly":      (0.5, 0.0, 0.5),
    "agree + consist":      (0.5, 0.5, 0.0),
}


def run(name, weights):
    cfg = json.loads(json.dumps(BASE))
    cfg["weight_agree"], cfg["weight_consist"], cfg["weight_anomaly"] = weights
    cfg["run_name"] = "ablation_" + name.replace(" ", "_").replace("/", "")
    f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    yaml.safe_dump(cfg, f)
    f.close()
    p = subprocess.run([sys.executable, "-m", "p2p", f.name, "--result", "json"],
                       capture_output=True, text=True, encoding="utf-8", cwd=HERE)
    os.unlink(f.name)
    if p.returncode != 0:
        return None
    path = os.path.join(HERE, "results", cfg["run_name"] + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    last = data["questions"][-1]["scores"]
    return {
        "separation": last.get("trust_separation"),
        "margin": last.get("separation_margin"),
        "influence": last.get("attacker_influence"),
        "false_alarm": last.get("false_alarm"),
        "found_in": last.get("detection_round"),
        "accuracy": last.get("honest_accuracy"),
    }


def show(v, kind="num"):
    if v is None:
        return "n/a"
    if kind == "pct":
        return f"{v:.1%}"
    if kind == "int":
        return str(v)
    return f"{v:+.3f}"


def main():
    print("Running each mix of signals. This calls a real model, please wait.\n")
    print(f"{'signals used':24} {'separation':>11} {'worst gap':>10} "
          f"{'influence':>10} {'false alarm':>12} {'found in':>9} {'accuracy':>9}")
    print("-" * 92)
    for name, weights in MIXES.items():
        r = run(name, weights)
        if r is None:
            print(f"{name:24} {'FAILED':>11}")
            continue
        print(f"{name:24} {show(r['separation']):>11} {show(r['margin']):>10} "
              f"{show(r['influence'],'pct'):>10} {show(r['false_alarm']):>12} "
              f"{show(r['found_in'],'int'):>9} {show(r['accuracy'],'pct'):>9}")
    print("-" * 92)
    print("How to read this:")
    print("  separation  gap between average honest trust and average liar trust. Higher is better.")
    print("  worst gap   least trusted honest agent minus most trusted liar. Above 0 is a clean split.")
    print("  influence   the liar's share of the talking. Lower is better. Equal share is 25%.")
    print("  false alarm spread among honest agents. Near 0 means nobody is unfairly punished.")
    print("  found in    how many rounds until the split was clean. Fewer is better.")
    print()
    print("If one signal on its own matches 'all three', the other two are not")
    print("earning their place and the formula could be simpler.")


if __name__ == "__main__":
    main()
