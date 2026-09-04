#!/usr/bin/env python3
"""Generate docs/assets/lessons.json and docs/assets/indicators.json.

The HTML Academy screens (learn.html, lesson.html, indicators.html) read these
two files. Lessons merge authored prose (scripts/learn_content.py) with the
canonical strategy catalog (docs/assets/strategies.json, itself generated from
bot.py) so default parameters, warm-ups and entry/exit texts never drift.

    python scripts/generate_learn_assets.py

The script validates every strategy id, checks that each lesson documents the
parameters the strategy actually has, and lists unknown concept links.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import learn_content  # noqa: E402

DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
CATALOG_PATH = os.path.join(DOCS, "assets", "strategies.json")

DIFFICULTY_NAMES = {1: "Beginner", 2: "Intermediate", 3: "Advanced"}

# Generic explanations for parameters shared by many strategies that lesson
# prose does not need to repeat.
GENERIC_PARAMS = {
    "alloc": {
        "what": "Share of the account's available cash spent on a single entry.",
        "effect": "None = the global default (95% of cash) applies. Lower it to trade smaller.",
    },
}

# Parameters whose keys appear in lessons but may intentionally not be in the
# catalog defaults dict (e.g. no-op placeholders) -- still warn, though.
_unknown_concepts: list = []


def build_lessons(catalog: list) -> list:
    lessons = []
    for cat in catalog:
        sid = cat["id"]
        prose = learn_content.LESSONS.get(sid)
        if prose is None:
            print(f"!! no lesson prose for {sid}", file=sys.stderr)
            continue

        params = {}
        for key, default in cat["params"].items():
            if key in prose.get("params", {}):
                params[key] = {"default": default, **prose["params"][key]}
            elif key in GENERIC_PARAMS:
                params[key] = {"default": default, **GENERIC_PARAMS[key]}
            else:
                print(f"!! param '{key}' of {sid} has no lesson explanation", file=sys.stderr)
                params[key] = {"default": default, "what": key, "effect": ""}
        # Prose may describe parameters that the catalog lacks -> flag it.
        for key in prose.get("params", {}):
            if key not in cat["params"]:
                print(f"!! lesson {sid} documents unknown param '{key}' (not in catalog)", file=sys.stderr)

        for concept in prose.get("concepts", []):
            if concept not in learn_content.CONCEPTS:
                _unknown_concepts.append((sid, concept))

        difficulty = int(prose.get("difficulty", 2))
        lessons.append(
            {
                "id": sid,
                "name": cat["name"],
                "category": cat["category"],
                "difficulty": difficulty,
                "level": DIFFICULTY_NAMES.get(difficulty, "Intermediate"),
                "warmup": cat["warmup"],
                "single_position": cat["single_position"],
                "entry": cat["entry"],
                "exit": cat["exit"],
                "params": params,
                "summary": prose["summary"],
                "idea": prose["idea"],
                "how": prose.get("how", []),
                "strengths": prose.get("strengths", []),
                "weaknesses": prose.get("weaknesses", []),
                "when": prose.get("when", []),
                "mistakes": prose.get("mistakes", []),
                "watch": prose.get("watch", []),
                "concepts": prose.get("concepts", []),
                "related": prose.get("related", []),
            }
        )
    for cat in catalog:
        if cat["id"] not in learn_content.LESSONS:
            print(f"!! catalog has {cat['id']} but no lesson prose", file=sys.stderr)
    return lessons


def build_indicators(lessons: list) -> list:
    used_by: dict = {}
    for lesson in lessons:
        for concept in lesson["concepts"]:
            used_by.setdefault(concept, []).append(lesson["id"])

    out = []
    for slug, entry in learn_content.CONCEPTS.items():
        out.append(
            {
                "id": slug,
                **entry,
                "used_by": sorted(used_by.get(slug, [])),
            }
        )
    for slug in used_by:
        if slug not in learn_content.CONCEPTS:
            print(f"!! lesson references unknown concept '{slug}'", file=sys.stderr)
    return out


def main() -> int:
    if not os.path.exists(CATALOG_PATH):
        print(f"Catalog not found: {CATALOG_PATH}\nRun scripts/generate_strategy_catalog.py first.")
        return 1
    with open(CATALOG_PATH, "r", encoding="utf-8") as fh:
        catalog = json.load(fh)

    lessons = build_lessons(catalog)
    indicators = build_indicators(lessons)

    for path, payload in (
        (os.path.join(DOCS, "assets", "lessons.json"), lessons),
        (os.path.join(DOCS, "assets", "indicators.json"), indicators),
    ):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        print(f"Wrote {len(payload)} entries to {os.path.relpath(path, os.getcwd())}")
    print(f"Concepts: {len(indicators)} | Lessons: {len(lessons)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
