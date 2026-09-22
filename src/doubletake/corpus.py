"""Blind and gold JSONL corpus loaders with strict field validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

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
