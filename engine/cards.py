"""Pure Python legal-placement enumeration and protected three-card draws.

Only event-category previews are generated here. Event resolution, placement
commits, resources, recovery tools and game-over decisions belong to later phases.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
import json
from math import exp, isfinite, log
from pathlib import Path
from random import Random
from typing import Literal

from engine.directions import rotate_doors
from engine.models import BOARD_SIZE, Board, Tile
from engine.placement import can_place, frontier_cells, reachable_rooms


Doors = tuple[bool, bool, bool, bool]
Position = tuple[int, int]
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "data" / "prototype_config.json"


def _weight(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite nonnegative number")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{label} must be finite") from error
    if not isfinite(result) or result < 0:
        raise ValueError(f"{label} must be a finite nonnegative number")
    return result


@dataclass(frozen=True)
class RoomType:
    """Normal-room template; zero weight suppresses extras, never protection."""

    kind: str
    doors: Doors
    weight: float
    event_weights: tuple[tuple[str, float], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not self.kind or self.kind.startswith("_"):
            raise ValueError("Room kind must be a nonempty name")
        if self.kind in {"start", "altar_a", "altar_b", "core"}:
            raise ValueError("Special rooms cannot be drawn as normal cards")
        if not isinstance(self.doors, tuple) or len(self.doors) != 4 or not all(
            type(door) is bool for door in self.doors
        ) or not any(self.doors):
            raise ValueError("Room doors must contain four N/E/S/W booleans and at least one door")
        _weight(self.weight, f"{self.kind}.weight")
        if not isinstance(self.event_weights, tuple) or not self.event_weights or any(
            not isinstance(pair, tuple) or len(pair) != 2 for pair in self.event_weights
        ):
            raise ValueError("Event weights must be a nonempty tuple of category/weight pairs")
        names = []
        for name, weight in self.event_weights:
            if not isinstance(name, str) or not name:
                raise ValueError("Event category names must be nonempty strings")
            names.append(name)
            _weight(weight, f"{self.kind}.{name}")
        if len(names) != len(set(names)) or not any(weight > 0 for _, weight in self.event_weights):
            raise ValueError("Event categories must be unique with a positive total weight")


@dataclass(frozen=True)
class CardConfig:
    """Validated snapshot of the provisional room and preview settings."""

    room_types: tuple[RoomType, ...]
    boost_second_legal_weight: float = 2.0

    def __post_init__(self) -> None:
        if not isinstance(self.room_types, tuple) or not self.room_types:
            raise ValueError("At least one normal room type is required")
        if not all(isinstance(room, RoomType) for room in self.room_types):
            raise ValueError("room_types must contain RoomType values")
        names = [room.kind for room in self.room_types]
        if len(names) != len(set(names)) or not any(room.weight > 0 for room in self.room_types):
            raise ValueError("Room kinds must be unique with a positive total weight")
        if _weight(self.boost_second_legal_weight, "boost_second_legal_weight") < 1:
            raise ValueError("boost_second_legal_weight must be at least 1")

    @classmethod
    def from_mapping(cls, data: Mapping) -> CardConfig:
        """Read card settings from the existing prototype JSON schema.

        Reject configurations that disable the confirmed three-card guarantee.
        Other sections (including event outcomes) are deliberately left unused.
        """
        try:
            if type(data["board"]["size"]) is not int or data["board"]["size"] != BOARD_SIZE:
                raise ValueError("Card generation requires a 7x7 board")
            draw = data["draw"]
            if type(draw["hand_size"]) is not int or draw["hand_size"] != 3:
                raise ValueError("Exactly three cards are required")
            if draw["guarantee_one_legal"] is not True:
                raise ValueError("Legal draw protection cannot be disabled")
            categories = data["events"]["categories"]
            if not isinstance(categories, list) or not categories or any(
                not isinstance(name, str) or not name for name in categories
            ) or len(categories) != len(set(categories)):
                raise ValueError("Event categories must be unique nonempty strings")
            room_types = []
            for kind, definition in sorted(data["room_types"].items()):
                if kind.startswith("_"):
                    continue  # Existing JSON uses _comment metadata.
                weights = data["events"]["weights_by_kind"][kind]
                if {key for key in weights if not key.startswith("_")} != set(categories):
                    raise ValueError(f"Event weights for {kind} must match the categories")
                room_types.append(RoomType(
                    kind=kind,
                    doors=tuple(definition["doors"]),
                    weight=_weight(definition["weight"], f"{kind}.weight"),
                    event_weights=tuple((name, _weight(weights[name], f"{kind}.{name}"))
                                        for name in sorted(categories)),
                ))
            return cls(tuple(room_types), draw["boost_second_legal_weight"])
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"Invalid card configuration: {error}") from error


def load_card_config(path: str | Path = DEFAULT_CONFIG_PATH) -> CardConfig:
    """Load a validated config; the default path is independent of working directory."""
    with Path(path).open(encoding="utf-8-sig") as source:
        return CardConfig.from_mapping(json.load(source))


@dataclass(frozen=True)
class Card:
    """Immutable shape and stable broad event preview; no event is executed."""

    kind: str
    doors: Doors
    event_category: str

    def rotated(self, times: int = 1) -> Card:
        """Return a rotated preview without changing the original card or category."""
        return replace(self, doors=rotate_doors(self.doors, times))


@dataclass(frozen=True)
class LegalPlacement:
    """One legal option; rotation is clockwise quarter-turns from the room template."""

    kind: str
    pos: Position
    rotation: int
    doors: Doors


@dataclass(frozen=True)
class DrawResult:
    """A snapshot for this board: ready has three cards; blocked has none.

    Legal placements must be recomputed and revalidated after a board/lock change.
    Blocked means no normal placement, not game over.
    """

    status: Literal["ready", "blocked"]
    cards: tuple[Card, ...]
    legal_placements: tuple[LegalPlacement, ...]

    @property
    def legal_card_indices(self) -> tuple[int, ...]:
        """Cards placeable in at least one orientation, for UI highlighting."""
        kinds = {placement.kind for placement in self.legal_placements}
        return tuple(index for index, card in enumerate(self.cards) if card.kind in kinds)


def unique_rotations(doors: Doors) -> tuple[tuple[int, Doors], ...]:
    """Return distinct (quarter-turns, doors), retaining the first equivalent rotation."""
    rotations = []
    seen = set()
    for turns in range(4):
        rotated = rotate_doors(doors, turns)
        if rotated not in seen:
            seen.add(rotated)
            rotations.append((turns, rotated))
    return tuple(rotations)


def enumerate_legal_placements(
    board: Board,
    start: Position,
    config: CardConfig | None = None,
    locked_specials: Collection[Position] = (),
) -> tuple[LegalPlacement, ...]:
    """Enumerate every reachable frontier x normal room x unique rotation.

    Stable ordering is position, kind, then rotation. Phase 1 APIs enforce board
    shape, all occupied-neighbor matches, reachability, and outward-door rules.
    """
    if config is None:
        config = load_card_config()
    reachable = reachable_rooms(board, start, locked_specials)
    placements = []
    for pos in sorted(frontier_cells(board, reachable)):
        for room in sorted(config.room_types, key=lambda room: room.kind):
            for turns, doors in unique_rotations(room.doors):
                if can_place(Tile(room.kind, doors), pos, board, reachable)[0]:
                    placements.append(LegalPlacement(room.kind, pos, turns, doors))
    return tuple(placements)


def _choose_room(
    rng: Random,
    rooms: Sequence[RoomType],
    boosted_kinds: set[str],
    boost: float,
) -> RoomType:
    log_boost = log(boost)
    # Apply the boost before normalization, without multiplying large floats or
    # dividing tiny weights to zero before the boost can take effect.
    log_weights = [log(room.weight) + (log_boost if room.kind in boosted_kinds else 0)
                   if room.weight > 0 else -float("inf") for room in rooms]
    maximum = max(log_weights)
    if maximum == -float("inf"):
        return rng.choice(rooms)  # The hard legal guarantee overrides zero draw weights.
    weights = [exp(weight - maximum) for weight in log_weights]
    return rng.choices(rooms, weights=weights, k=1)[0]


def draw_cards(
    board: Board,
    start: Position,
    *,
    rng: Random,
    config: CardConfig | None = None,
    locked_specials: Collection[Position] = (),
) -> DrawResult:
    """Draw exactly three cards with one legal guarantee and no reroll loop.

    Pass a dedicated Random(seed) and retain it across turns for reproducibility.
    Remaining slots boost distinct legal geometries without guaranteeing a second
    choice. No legal placements returns blocked without consuming random state.
    """
    if config is None:
        config = load_card_config()
    legal = enumerate_legal_placements(board, start, config, locked_specials)
    if not legal:
        return DrawResult("blocked", (), ())

    rooms = sorted(config.room_types, key=lambda room: room.kind)
    legal_kinds = {placement.kind for placement in legal}
    selected = [_choose_room(rng, [room for room in rooms if room.kind in legal_kinds], set(), 1)]
    for _ in range(2):
        chosen_shapes = {min(doors for _, doors in unique_rotations(room.doors)) for room in selected}
        boosted = {room.kind for room in rooms if room.kind in legal_kinds
                   and min(doors for _, doors in unique_rotations(room.doors)) not in chosen_shapes}
        selected.append(_choose_room(rng, rooms, boosted, config.boost_second_legal_weight))

    cards = []
    for room in selected:
        names, weights = zip(*room.event_weights)
        maximum = max(weights)
        category = rng.choices(names, weights=[weight / maximum for weight in weights], k=1)[0]
        cards.append(Card(room.kind, room.doors, category))
    rng.shuffle(cards)
    return DrawResult("ready", tuple(cards), legal)
