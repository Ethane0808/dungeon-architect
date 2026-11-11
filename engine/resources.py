"""Immutable, bounded player resources; no input or rendering dependencies."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
import json
from pathlib import Path

from engine.cards import DEFAULT_CONFIG_PATH


def _integer(value: object, name: str) -> int:
    if type(value) is not int:
        raise ValueError(f"{name} must be an integer")
    return value


@dataclass(frozen=True)
class Resources:
    """Validated resource snapshot. Changes return a new, clamped snapshot.

    HP is bounded by 0 and hp_max. Supplies use supplies_min (default 0) and
    supplies_max; None removes the upper limit. Zero HP is exposed as a flag,
    without deciding whether the game has ended.
    """

    hp: int
    hp_max: int
    supplies: int
    supplies_max: int | None = None
    supplies_min: int = 0

    def __post_init__(self) -> None:
        for name in ("hp", "hp_max", "supplies", "supplies_min"):
            _integer(getattr(self, name), name)
        if self.hp_max <= 0 or not 0 <= self.hp <= self.hp_max:
            raise ValueError("HP must be between 0 and a positive hp_max")
        if self.supplies_min < 0 or self.supplies < self.supplies_min:
            raise ValueError("Supplies must be at least a nonnegative supplies_min")
        if self.supplies_max is not None:
            _integer(self.supplies_max, "supplies_max")
            if self.supplies_max < self.supplies_min or self.supplies > self.supplies_max:
                raise ValueError("Supplies must not exceed supplies_max")

    @property
    def hp_depleted(self) -> bool:
        return self.hp == 0

    def apply(self, *, hp_delta: int = 0, supplies_delta: int = 0) -> "Resources":
        """Apply integer deltas, clamping to bounds; leave this snapshot intact."""
        hp = min(self.hp_max, max(0, self.hp + _integer(hp_delta, "hp_delta")))
        supplies = max(self.supplies_min, self.supplies + _integer(supplies_delta, "supplies_delta"))
        if self.supplies_max is not None:
            supplies = min(self.supplies_max, supplies)
        return replace(self, hp=hp, supplies=supplies)

    @classmethod
    def from_mapping(cls, data: Mapping) -> "Resources":
        """Read initial values from the provisional prototype player section."""
        try:
            player = data["player"]
            return cls(hp=player["hp_initial"], hp_max=player["hp_max"],
                       supplies=player["supplies_initial"], supplies_max=player.get("supplies_max"),
                       supplies_min=player.get("supplies_min", 0))
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"Invalid player configuration: {error}") from error


def load_resources(path: str | Path = DEFAULT_CONFIG_PATH) -> Resources:
    """Load provisional initial resources, independent of the working directory."""
    with Path(path).open(encoding="utf-8-sig") as source:
        return Resources.from_mapping(json.load(source))
