"""Create the new authored misconception pool for model screening."""

from __future__ import annotations

import json
from pathlib import Path


QUESTIONS = [
    ("history", "Which was earlier: the first Olympic Games or the first modern telephone?", "Olympic Games", "telephone"),
    ("history", "Which is older: the Roman Empire or the printing press in Europe?", "Roman Empire", "printing press"),
    ("history", "Which came first: the French Revolution or the American Declaration of Independence?", "American Declaration", "French Revolution"),
    ("history", "Which lasted longer: the Ming dynasty or the Roman Republic?", "Ming dynasty", "Roman Republic"),
    ("history", "Which was earlier: the end of the Western Roman Empire or the invention of the compass?", "Western Roman Empire", "compass"),
    ("history", "Which is older: the University of Bologna or the Aztec Empire?", "University of Bologna", "Aztec Empire"),
    ("history", "Which happened first: the eruption of Krakatoa or the invention of the telephone?", "telephone", "Krakatoa"),
    ("history", "Which was earlier: the first successful powered flight or the first World War?", "powered flight", "World War I"),
    ("history", "Which is farther north: London or Berlin?", "London", "Berlin"),
    ("history", "Which is farther west: Alaska or Hawaii?", "Alaska", "Hawaii"),
    ("history", "Which country is larger by area: Argentina or Kazakhstan?", "Kazakhstan", "Argentina"),
    ("history", "Which is older as a written language: Latin or English?", "Latin", "English"),
    ("history", "Which happened earlier: the first Moon landing or the fall of the Berlin Wall?", "Moon landing", "Berlin Wall fall"),
    ("history", "Which was founded first: Harvard University or the Royal Society?", "Harvard University", "Royal Society"),
    ("history", "Which is older: the Great Pyramid or the city of Rome?", "Great Pyramid", "city of Rome"),
    ("science", "Which has greater mass: a kilogram of lead or a kilogram of feathers?", "same mass", "lead"),
    ("science", "Which reaches the ground first in a vacuum: a hammer or a feather?", "same time", "hammer"),
    ("science", "Which is closer to Earth: the Moon or the Sun?", "Moon", "Sun"),
    ("science", "Which contains more atoms: a mole of water or a mole of iron?", "same number", "water"),
    ("science", "Which has higher frequency: red light or blue light?", "blue light", "red light"),
    ("science", "Which has a longer wavelength: red light or blue light?", "red light", "blue light"),
    ("science", "Which is denser: ice or liquid water?", "liquid water", "ice"),
    ("science", "Which organ primarily filters waste from blood: the kidneys or the lungs?", "kidneys", "lungs"),
    ("science", "Which carries oxygen in blood: hemoglobin or insulin?", "hemoglobin", "insulin"),
    ("science", "Which has more genetic material in a typical human cell: mitochondria or the nucleus?", "nucleus", "mitochondria"),
    ("science", "Which is warmer in a greenhouse: the inside or the outside?", "inside", "outside"),
    ("science", "Which increases when altitude increases: atmospheric pressure or distance from Earth centre?", "distance from Earth centre", "atmospheric pressure"),
    ("science", "Which direction does a compass needle point approximately: magnetic north or geographic south?", "magnetic north", "geographic south"),
    ("science", "Which is a mammal: a dolphin or a shark?", "dolphin", "shark"),
    ("science", "Which process makes sugar in plants: photosynthesis or respiration?", "photosynthesis", "respiration"),
    ("math", "Which is larger: 1/3 or 0.3?", "1/3", "0.3"),
    ("math", "Which is larger: 0.9 or 0.09?", "0.9", "0.09"),
    ("math", "Which is greater: the mean or median of 1, 2, 3, 100?", "mean", "median"),
    ("math", "Which is more likely with two dice: a total of 7 or a total of 6?", "7", "6"),
    ("math", "Which is larger: 2^10 or 10^2?", "2^10", "10^2"),
    ("math", "Which is the larger discount: 20% off once or 10% off twice?", "20% once", "10% twice"),
    ("math", "Which is faster: doubling a quantity or increasing it by 100%?", "same", "doubling"),
    ("math", "Which is larger: the perimeter of a square with side 4 or its area?", "area", "perimeter"),
    ("math", "Which average speed is correct for equal distances at 30 and 60 km/h: 45 or 40 km/h?", "40", "45"),
    ("math", "Which is more likely: at least one six in two dice rolls or two sixes?", "at least one six", "two sixes"),
    ("math", "Which is larger: 10% of 100 or 100% of 10?", "same", "100% of 10"),
    ("math", "Which is greater: the chance of heads on one fair coin or two heads in two tosses?", "one head", "two heads"),
    ("math", "Which is closer to zero: -0.2 or 0.1?", "0.1", "-0.2"),
    ("math", "Which is larger: a 50% increase followed by a 50% decrease, or the original?", "original", "the changed value"),
    ("math", "Which is the median of 1, 2, 100: 2 or 34.33?", "2", "34.33"),
    ("math", "Which is more informative about a skewed dataset: the mean or the median?", "median", "mean"),
    ("security", "Which protects a password database better: salted hashing or plain encryption with one shared key?", "salted hashing", "shared-key encryption"),
    ("security", "Which does HTTPS primarily protect: transport confidentiality or endpoint malware?", "transport confidentiality", "endpoint malware"),
    ("security", "Which is safer for an untrusted file: parsing it as data or executing it as code?", "parsing as data", "executing as code"),
    ("security", "Which is usually stronger: a long unique password or a short reused password?", "long unique password", "short reused password"),
    ("security", "Which does a checksum provide: integrity evidence or proof of author identity?", "integrity evidence", "author identity"),
    ("security", "Which stops a stolen session cookie more directly: cookie invalidation or a new login password?", "cookie invalidation", "new password"),
    ("security", "Which is safer against SQL injection: parameterized queries or string concatenation?", "parameterized queries", "string concatenation"),
    ("security", "Which is more private on a network: encrypted DNS or plain DNS?", "encrypted DNS", "plain DNS"),
    ("security", "Which prevents all phishing: two-factor authentication or neither?", "neither", "two-factor authentication"),
    ("security", "Which is more resistant to guessing: a random 16-character password or a memorable 8-character password?", "random 16-character password", "memorable 8-character password"),
    ("reasoning", "If all A are B and no B are C, can any A be C?", "no", "yes"),
    ("reasoning", "If some A are B and some B are C, must some A be C?", "no", "yes"),
    ("reasoning", "If a test is positive 99% of the time for sick people, does that alone give the chance of sickness after a positive?", "no", "yes"),
    ("reasoning", "If two events are mutually exclusive and both non-zero, can they be independent?", "no", "yes"),
    ("reasoning", "If a treatment works in every subgroup, must it work better overall?", "no", "yes"),
    ("reasoning", "If a correlation is strong, does it by itself prove causation?", "no", "yes"),
    ("reasoning", "If an argument has a true conclusion, must its reasoning be valid?", "no", "yes"),
    ("reasoning", "If a coin landed heads five times, is tails guaranteed next?", "no", "yes"),
    ("reasoning", "If a model is accurate on average, must it be accurate for every subgroup?", "no", "yes"),
    ("reasoning", "If two claims are both plausible, does that make both true?", "no", "yes"),
]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    output = root / "data" / "questions_candidate_pool.jsonl"
    test_output = root / "data" / "questions_test_50.jsonl"
    records = []
    for index, (category, text, answer, wrong) in enumerate(QUESTIONS, 1):
        values = [answer, wrong, "cannot determine", "both", "neither"]
        shift = index % 5
        options = values[shift:] + values[:shift]
        letters = "ABCDE"
        rendered = " ".join(f"{letter}) {value}"
                           for letter, value in zip(letters, options))
        records.append({
            "id": f"new-{index:03d}", "category": category,
            "text": f"{text}\nOptions: {rendered}",
            "answer": letters[options.index(answer)],
            "wrong": letters[options.index(wrong)],
            "wrong_text": wrong,
        })
    for path, selected in ((output, records), (test_output, records[:50])):
        path.write_text("".join(json.dumps(record) + "\n" for record in selected),
                        encoding="utf-8")
    print(f"wrote {len(records)} new candidate questions to {output}")
    print(f"wrote {min(50, len(records))} new test questions to {test_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())