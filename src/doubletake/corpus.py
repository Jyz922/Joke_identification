"""Blind and gold JSONL corpus loaders with strict field validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .enums import Genre, MainClassification


@dataclass
class BlindItem:
    id: str
    text: str
    target_ages: list[int]


@dataclass
class GoldItem:
    id: str
    gold_label: MainClassification
    genre: Genre
    ambiguous_term: str
    sense_a: str
    sense_b: str
    expected_age_verdict: dict[str, str]


_BLIND_REQUIRED: frozenset[str] = frozenset({"id", "text", "target_ages"})
_GOLD_REQUIRED: frozenset[str] = frozenset({
    "id",
    "gold_label",
    "genre",
    "ambiguous_term",
    "sense_a",
    "sense_b",
    "expected_age_verdict",
})


def load_blind(path: str | Path) -> list[BlindItem]:
    """Load and validate a blind JSONL corpus file.

    Raises ValueError on malformed JSON, missing fields, unknown fields,
    or duplicate ids.
    """
    items: list[BlindItem] = []
    seen_ids: set[str] = set()

    for lineno, raw_line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"blind corpus line {lineno}: invalid JSON — {exc}"
            ) from exc

        _check_fields(obj, _BLIND_REQUIRED, lineno, "blind")

        item_id = obj["id"]
        if item_id in seen_ids:
            raise ValueError(
                f"blind corpus line {lineno}: duplicate id '{item_id}'"
            )
        seen_ids.add(item_id)

        items.append(BlindItem(
            id=item_id,
            text=obj["text"],
            target_ages=obj["target_ages"],
        ))

    return items


def load_gold(path: str | Path) -> dict[str, GoldItem]:
    """Load and validate a gold JSONL corpus file.

    Returns a dict keyed by item id.

    Raises ValueError on malformed JSON, missing fields, unknown fields,
    or duplicate ids.
    """
    items: dict[str, GoldItem] = {}

    for lineno, raw_line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), 1
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"gold corpus line {lineno}: invalid JSON — {exc}"
            ) from exc

        _check_fields(obj, _GOLD_REQUIRED, lineno, "gold")

        item_id = obj["id"]
        if item_id in items:
            raise ValueError(
                f"gold corpus line {lineno}: duplicate id '{item_id}'"
            )

        items[item_id] = GoldItem(
            id=item_id,
            gold_label=MainClassification(obj["gold_label"]),
            genre=Genre(obj["genre"]),
            ambiguous_term=obj["ambiguous_term"],
            sense_a=obj["sense_a"],
            sense_b=obj["sense_b"],
            expected_age_verdict=obj["expected_age_verdict"],
        )

    return items


def join_blind_gold(
    blind: list[BlindItem],
    gold: dict[str, GoldItem],
) -> list[tuple[BlindItem, GoldItem]]:
    """Pair blind items with their gold annotations.

    Raises ValueError if any gold id is absent from the blind set.
    Returns only items present in both sets (blind items without gold are
    included in runs but skipped here).
    """
    blind_ids = {item.id for item in blind}
    gold_only = set(gold) - blind_ids
    if gold_only:
        raise ValueError(
            f"Gold ids not found in blind set: {sorted(gold_only)}"
        )
    return [(item, gold[item.id]) for item in blind if item.id in gold]


def evaluate_run(
    records_path: str | Path,
    gold_path: str | Path,
) -> dict[str, Any]:
    """Evaluate pipeline execution records against a gold annotated corpus.

    Calculates:
      - Main classification accuracy & confusion matrix
      - Age-level verdict match rate
    """
    gold_dict = load_gold(gold_path)
    records: list[dict[str, Any]] = [
        json.loads(line)
        for line in Path(records_path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    total_items = 0
    correct_classification = 0
    total_age_evals = 0
    correct_age_evals = 0
    classification_confusion: dict[str, dict[str, int]] = {}

    for rec in records:
        item_id = rec.get("item_id")
        if item_id not in gold_dict:
            continue

        gold = gold_dict[item_id]
        total_items += 1

        final = rec.get("final") or {}
        pred_label = final.get("main_classification", "UNKNOWN")
        gold_label = (
            gold.gold_label.value
            if hasattr(gold.gold_label, "value")
            else str(gold.gold_label)
        )

        if pred_label == gold_label:
            correct_classification += 1

        if gold_label not in classification_confusion:
            classification_confusion[gold_label] = {}
        classification_confusion[gold_label][pred_label] = (
            classification_confusion[gold_label].get(pred_label, 0) + 1
        )

        per_age = final.get("per_age", {})
        for age_str, expected in gold.expected_age_verdict.items():
            age_int = int(age_str)
            age_actual = per_age.get(str(age_int)) or per_age.get(age_int)
            total_age_evals += 1
            if age_actual:
                appr = age_actual.get("appropriateness")
                comp = age_actual.get("comprehension")
                if expected in (appr, comp):
                    correct_age_evals += 1

    return {
        "total_items": total_items,
        "classification_accuracy": (
            round(correct_classification / total_items, 4) if total_items else 0.0
        ),
        "correct_classification": correct_classification,
        "total_age_evals": total_age_evals,
        "age_accuracy": (
            round(correct_age_evals / total_age_evals, 4) if total_age_evals else 0.0
        ),
        "correct_age_evals": correct_age_evals,
        "confusion_matrix": classification_confusion,
    }


def _check_fields(
    obj: dict,
    required: frozenset[str],
    lineno: int,
    corpus: str,
) -> None:
    missing = required - set(obj)
    if missing:
        raise ValueError(
            f"{corpus} corpus line {lineno}: "
            f"missing required fields {sorted(missing)}"
        )
    extra = set(obj) - required
    if extra:
        raise ValueError(
            f"{corpus} corpus line {lineno}: "
            f"unknown fields {sorted(extra)}"
        )
