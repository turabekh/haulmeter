"""AI-CONTEXT: `make ratecon-eval` — how often the parse is RIGHT on real paper (J1-A1).

    make ratecon-eval DIR=/path/to/corpus

A corpus is a directory of rate cons and their expectations, side by side:

    coyote-01.pdf    coyote-01.json
    tql-04.jpg       tql-04.json

Each `.json` states what the document actually prints, and `null` is a real answer:

    {"format": "coyote", "counterparty_email": "ap@coyote.example",
     "counterparty_phone": "7045550134", "broker_name": "Coyote Logistics"}

**THE CORPUS IS NOT IN THIS REPOSITORY AND MUST NOT BE.** A rate confirmation is a
counterparty's document carrying a broker's contract terms, their staff's names and
their addresses; this repository is public. `DIR` points outside the tree and the
default below is gitignored.

WHY THIS IS NOT A PYTEST. It calls the real model, costs money per run, and answers a
question that has no fixed answer — "how often is the parse right", not "does the code
do what it was written to do". Pinning a number like that in CI would either make the
suite flaky or make the number meaningless the first time somebody relaxed it to get
green. It is a MEASUREMENT, run when the prompt changes and recorded in the handoff.

The scoreboard weights the negative cases, because they are the ones with a victim:

  · CORRECT      the value the document prints, extracted
  · ABSENT-OK    the document prints nothing, and the parse said nothing
  · MISSED       the document prints it, the parse returned null — costs typing
  · WRONG        the document prints X, the parse returned Y
  · INVENTED     the document prints NOTHING and the parse returned an address

INVENTED is fatal on its own and the report says so at any count above zero. A missed
address costs a driver thirty seconds of typing; an invented one addresses a stranger a
load's details, and the driver confirming it has no way to know — the field looks
exactly the same whether the address was read or imagined.
"""

import base64
import json
import os
import sys
from pathlib import Path

from app.core.db import SessionLocal
from app.foundation.f05_load import public as loads
from app.foundation.f09_ai_gateway import public as ai

DEFAULT_DIR = "/corpus/ratecon"

# E2-FR-style floors: below either of these the run is a sample, not a validation. Three
# formats because one broker's template proves the parse reads THAT template.
REQUIRED_DOCS = 10
REQUIRED_FORMATS = 3

MEDIA = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

# what this eval scores. Deliberately the contact fields plus the two money terms a
# claim is argued from — the whole schema would dilute the number that matters.
FIELDS = ("counterparty_email", "counterparty_phone", "detention_rate_cents_per_hour")


def _load_corpus(root: Path) -> list[tuple[Path, dict]]:
    pairs = []
    for doc in sorted(root.iterdir()):
        if doc.suffix.lower() not in MEDIA:
            continue
        expected = doc.with_suffix(".json")
        if not expected.exists():
            print(f"  {doc.name}: no {expected.name} beside it — skipped")
            continue
        pairs.append((doc, json.loads(expected.read_text())))
    return pairs


def _normalise(field: str, value):
    """Hold the EXPECTATION to the same normaliser the parse output goes through, so a
    corpus written as "(704) 555-0134" is not scored WRONG against "7045550134"."""
    if value is None:
        return None
    if field == "counterparty_email":
        return loads.parsed_email({"counterparty_email": value})
    if field == "counterparty_phone":
        return loads.parsed_phone({"counterparty_phone": value})
    return value


def _score(field: str, expected, got) -> str:
    expected = _normalise(field, expected)
    got = _normalise(field, got)
    if expected is None and got is None:
        return "ABSENT-OK"
    if expected is None:
        return "INVENTED"
    if got is None:
        return "MISSED"
    return "CORRECT" if expected == got else "WRONG"


def main() -> int:
    # `or` rather than a default argument: `make ratecon-eval` with no DIR= passes the
    # variable through EMPTY, and Path("") is the working directory — which is a real
    # directory, so the "point me at a corpus" message would never print and the run
    # would report zero pairs from the source tree instead.
    root = Path(os.environ.get("DIR") or DEFAULT_DIR)
    if not root.is_dir():
        print(f"no corpus at {root}")
        print("usage: make ratecon-eval DIR=/path/to/corpus")
        print("the corpus lives OUTSIDE this repository — rate cons are counterparty")
        print("documents and this repository is public")
        return 1

    pairs = _load_corpus(root)
    if not pairs:
        print(f"{root} holds no rate con / expectation pairs")
        return 1

    provider = ai.resolve_provider()
    results = []
    with SessionLocal() as db:
        for doc, expected in pairs:
            b64 = base64.b64encode(doc.read_bytes()).decode()
            try:
                parsed = loads.parse_rate_con(
                    db,
                    provider,
                    doc.name,
                    document_b64=b64,
                    media_type=MEDIA[doc.suffix.lower()],
                )
            except Exception as exc:  # noqa: BLE001 — an unreadable document is a result
                print(f"  {doc.name}: parse failed — {type(exc).__name__}: {exc}")
                results.append((doc.name, expected.get("format", "?"), None, {}))
                continue
            scores = {f: _score(f, expected.get(f), parsed.get(f)) for f in FIELDS}
            results.append((doc.name, expected.get("format", "?"), parsed, scores))
        # a measurement must not leave rows behind in the database it measured against
        db.rollback()

    formats = {fmt for _, fmt, _, _ in results}
    print("\n" + "=" * 72)
    print(f"rate-con parse eval · {len(results)} documents · {len(formats)} formats")
    print(f"prompt: {loads.RATE_CON_PROMPT}")
    print("=" * 72 + "\n")

    print("| document | format | " + " | ".join(FIELDS) + " |")
    print("|---" * (2 + len(FIELDS)) + "|")
    tally: dict[str, int] = {}
    for name, fmt, parsed, scores in results:
        if parsed is None:
            print(f"| `{name}` | {fmt} | " + " | ".join(["PARSE FAILED"] * len(FIELDS)) + " |")
            tally["PARSE FAILED"] = tally.get("PARSE FAILED", 0) + 1
            continue
        print(f"| `{name}` | {fmt} | " + " | ".join(scores[f] for f in FIELDS) + " |")
        for verdict in scores.values():
            tally[verdict] = tally.get(verdict, 0) + 1

    print("\n" + " · ".join(f"**{v}** {k}" for k, v in sorted(tally.items())))

    invented = tally.get("INVENTED", 0)
    if invented:
        print(
            f"\n> **{invented} INVENTED value(s).** The document printed nothing and the "
            "parse produced one anyway. This is the failure with a victim: a driver "
            "confirming a prefilled address cannot tell a read one from an imagined one. "
            "`j1_contact_parse` does not go on while this is above zero."
        )
    if len(results) < REQUIRED_DOCS or len(formats) < REQUIRED_FORMATS:
        print(
            f"\n> This run is a SAMPLE, not a validation: {len(results)}/{REQUIRED_DOCS} "
            f"documents across {len(formats)}/{REQUIRED_FORMATS} broker formats. One "
            "broker's template proves the parse reads that template."
        )
    elif not invented:
        print("\n**The corpus floors are met and nothing was invented.**")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
