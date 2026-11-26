"""Run successive MVP floors with reproducible seeds and shared resources."""

from dataclasses import replace
import json
from pathlib import Path
from random import Random

from engine.mvp import GameStatus, MvpSession


DIFFICULTY_PATH = Path(__file__).resolve().parents[1] / "data" / "endless_difficulty.json"


class DifficultyError(ValueError):
    """The player can correct the settings and retry the same floor."""


def floor_settings(path, floor):
    """Read on floor entry, validating every tier before accepting the file."""
    with Path(path).open(encoding="utf-8-sig") as source:
        data = json.load(source)
    if not isinstance(data, dict) or not isinstance(data.get("tiers"), list) or not data["tiers"]:
        raise ValueError("Expected a nonempty tiers list")
    events = data.get("events", {})
    limits = {"bell_percent": (0, 100), "danger_bonus_percent": (0, 1000),
              "danger_half_bonus_floors": (1, None)}
    if not isinstance(events, dict):
        raise ValueError("Expected an events object")
    for key, value in events.items():
        if key == "special_weights":
            if isinstance(value, dict) and "puzzle" in value:
                value.setdefault("casino", value.pop("puzzle"))
            if (not isinstance(value, dict) or set(value) - {"relic", "monster", "fog", "casino"}
                    or any(type(w) is not int or w < 0 for w in value.values()) or not any(value.values())):
                raise ValueError("special_weights needs known outcomes and at least one positive integer weight")
            continue
        if key not in limits or type(value) is not int:
            raise ValueError(f"Invalid event setting: {key}")
        minimum, maximum = limits[key]
        if value < minimum or (maximum is not None and value > maximum):
            raise ValueError(f"Invalid event value: {key}")
    previous = 0
    for tier in data["tiers"]:
        if not isinstance(tier, dict) or set(tier) != {"from_floor", "guard_build_limit", "variants"}:
            raise ValueError("Each tier needs from_floor, guard_build_limit and variants")
        start, limit, variants = tier["from_floor"], tier["guard_build_limit"], tier["variants"]
        if type(start) is not int or start <= previous or (previous == 0 and start != 1):
            raise ValueError("from_floor must start at 1 and increase")
        if type(limit) is not int or limit < 1 or not isinstance(variants, list) or not variants:
            raise ValueError("Expected a positive guard_build_limit and nonempty variants")
        for variant in variants:
            if not isinstance(variant, dict):
                raise ValueError("Expected a variant object")
            for key, value in variant.items():
                if key == "spring_position" and value in ("near_start", "far_from_start", "random"):
                    continue
                if key in ("rubble_count", "spring_count", "chisel_uses", "seal_uses") and type(value) is int and value >= 0:
                    continue
                raise ValueError(f"Invalid variant setting: {key}")
        if start <= floor:
            selected = limit, variants[(floor - start) % len(variants)]
        previous = start
    limit, variant = selected
    return limit, variant, events


def _floor_cards(config, number, events):
    depth = number - 1
    bonus = events.get("danger_bonus_percent", 0) / 100
    if not depth or not bonus:
        return config
    multiplier = 1 + bonus * depth / (depth + events.get("danger_half_bonus_floors", 5))
    rooms = tuple(replace(room, event_weights=tuple(
        (name, weight * multiplier if name == "danger" else weight)
        for name, weight in room.event_weights
    )) for room in config.room_types)
    return replace(config, room_types=rooms)


class EndlessRun:
    def __init__(self, expedition: MvpSession, difficulty_path=DIFFICULTY_PATH):
        self.seed = expedition.seed
        self.template = expedition
        self.difficulty_path = difficulty_path
        self.restart()

    def _make_floor(self, number, resources):
        seed = self.seed if number == 1 else Random(f"endless:{self.seed}:{number}").randrange(1_000_000)
        try:
            limit, variant, events = floor_settings(self.difficulty_path, number)
        except (ValueError, OSError) as exc:
            raise DifficultyError(str(exc)) from exc
        terrain = {k: v for k, v in variant.items() if k in ("rubble_count", "spring_count", "spring_position")}
        bell = number > 1 and Random(f"bells:{seed}").randrange(100) < events.get("bell_percent", 0)
        if number == 1:
            terrain["spring_count"] = 1
        level = replace(self.template.level, guard_build_limit=limit, well_kind="bell" if bell else "spring",
                        **terrain)
        tools = self.template.tools
        for key, tool in (("chisel_uses", "emergency_chisel"), ("seal_uses", "door_seal")):
            if key in variant:
                tools = replace(tools, **{tool: replace(getattr(tools, tool), max_uses_per_game=variant[key])})
        return MvpSession(seed, _floor_cards(self.template.config, number, events), resources=resources,
                          special_weights=tuple(sorted(events.get("special_weights", {}).items())),
                          event_config=self.template.event_config,
                          level=level, tools=tools)

    def restart(self):
        self.session = self._make_floor(1, self.template.initial_resources)
        self.floor = 1
        self.ended = False

    @property
    def completed(self):
        return self.floor - 1 + (self.session.status == GameStatus.WON)

    @property
    def can_advance(self):
        return not self.ended and self.session.status == GameStatus.WON

    def advance(self):
        if not self.can_advance:
            return False
        self.session = self._make_floor(self.floor + 1, self.session.resources)
        self.floor += 1
        return True
