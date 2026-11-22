"""Configurable first-entry outcomes and notifications, independent of pygame.

The card system already samples geometry-dependent categories using the session
seed. First entry samples a variant using a separate, location-specific seed.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from random import Random

from engine.cards import DEFAULT_CONFIG_PATH, Position
from engine.resources import Resources, _integer


@dataclass(frozen=True)
class EventOutcome:
    """One configured effect; all numerical values are playtesting settings."""

    message: str
    hp_delta: int = 0
    supplies_delta: int = 0
    trapped_cache: int = 0
    weight: int = 1
    icon: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("Event message must be a nonempty string")
        _integer(self.hp_delta, "hp_delta")
        _integer(self.supplies_delta, "supplies_delta")
        if _integer(self.weight, "weight") < 1:
            raise ValueError("Event weight must be positive")
        if _integer(self.trapped_cache, "trapped_cache") < 0:
            raise ValueError("Trapped cache contents cannot be negative")

    @classmethod
    def from_mapping(cls, effect: Mapping, category: str) -> "EventOutcome":
        fields = {k: v for k, v in effect.items() if not k.startswith("_")}
        fields.setdefault("message", f"You explored a {category} room.")
        return cls(**fields)


@dataclass(frozen=True)
class EventNotification:
    """Last resolved event, with actual resource changes after bounds apply."""

    pos: Position
    category: str
    message: str
    hp_delta: int
    supplies_delta: int
    trapped_cache: int = 0
    loops_closed: int = 0
    loop_supplies: int = 0
    icon: str = ""


@dataclass(frozen=True)
class EventConfig:
    outcomes: tuple[tuple[str, EventOutcome], ...]
    variants: tuple[tuple[str, tuple[EventOutcome, ...]], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.outcomes, tuple) or not self.outcomes:
            raise ValueError("At least one event outcome is required")
        names = []
        for pair in self.outcomes:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("Outcomes must be category/EventOutcome pairs")
            category, outcome = pair
            if not isinstance(category, str) or not category or category.startswith("_"):
                raise ValueError("Event category must be a nonempty name")
            if not isinstance(outcome, EventOutcome):
                raise ValueError("Event effects must be EventOutcome values")
            names.append(category)
        if len(set(names)) != len(names):
            raise ValueError("Event categories must be unique")

    def outcome_for(self, category: str) -> EventOutcome:
        for name, outcome in self.outcomes:
            if name == category:
                return outcome
        raise ValueError(f"No configured outcome for event category {category!r}")

    @classmethod
    def from_mapping(cls, data: Mapping) -> "EventConfig":
        try:
            events = data["events"]
            categories = events["categories"]
            if not isinstance(categories, list) or not categories or any(
                not isinstance(name, str) or not name for name in categories
            ) or len(categories) != len(set(categories)):
                raise ValueError("Event categories must be unique nonempty strings")
            definitions = events["outcomes"]
            if {name for name in definitions if not name.startswith("_")} != set(categories):
                raise ValueError("Event outcomes must match configured categories")
            outcomes = []
            variants = []
            for category in sorted(categories):
                effect = definitions[category]
                if not isinstance(effect, Mapping):
                    raise ValueError("Each event outcome must be an object")
                effect = dict(effect)
                alternatives = effect.pop("variants", [])
                if not isinstance(alternatives, list):
                    raise ValueError("Event variants must be a list of effects")
                base = EventOutcome.from_mapping(effect, category)
                outcomes.append((category, base))
                if alternatives:
                    variants.append((category, tuple(EventOutcome.from_mapping(v, category) for v in alternatives)))
            return cls(tuple(outcomes), tuple(variants))
        except (KeyError, TypeError, AttributeError) as error:
            raise ValueError(f"Invalid event configuration: {error}") from error


def load_event_config(path: str | Path = DEFAULT_CONFIG_PATH) -> EventConfig:
    with Path(path).open(encoding="utf-8-sig") as source:
        return EventConfig.from_mapping(json.load(source))


def resolve_event(category: str, pos: Position, resources: Resources,
                  config: EventConfig, seed: int | None = None) -> tuple[Resources, EventNotification]:
    """Prepare bounded resources and a notification without mutating game state."""
    outcome = config.outcome_for(category)
    if seed is not None:
        alternatives = dict(config.variants).get(category)
        if alternatives:
            rng = Random(f"{seed}:{pos[0]}:{pos[1]}:{category}")
            options = (outcome, *alternatives)
            # Keep the original seeded first draw. Thin lower-weight outcomes
            # by accepting each candidate in proportion to its weight.
            maximum = max(option.weight for option in options)
            while True:
                outcome = rng.choice(options)
                if rng.randrange(maximum) < outcome.weight:
                    break
    updated = resources.apply(hp_delta=outcome.hp_delta, supplies_delta=outcome.supplies_delta)
    return updated, EventNotification(pos, category, outcome.message,
                                      updated.hp - resources.hp, updated.supplies - resources.supplies,
                                      outcome.trapped_cache, icon=outcome.icon or category)
