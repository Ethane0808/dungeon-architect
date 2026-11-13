"""Fixed-level validation without assuming card draws guarantee solvability."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json

import pytest

from engine.cards import DEFAULT_CONFIG_PATH
from engine.level import LevelConfig, SpecialRoom, load_level_config
from engine.models import BOARD_SIZE


@pytest.fixture
def raw_level():
    return json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


def test_default_level_loads_provisional_positions_and_geometry():
    level = load_level_config()
    assert level.start == SpecialRoom("start", (3, 0), (True, True, True, False))
    assert level.altars == (
        SpecialRoom("altar_a", (0, 6), (False, False, True, True)),
        SpecialRoom("altar_b", (6, 6), (True, False, False, True)),
    )
    assert level.core == SpecialRoom("core", (3, 6), (True, False, True, True))
    assert level.first_altar_supplies == 1


def test_make_board_initializes_only_special_rooms_and_creates_independent_tiles():
    level = load_level_config()
    first, second = level.make_board(), level.make_board()
    expected = {room.pos: room for room in (level.start, *level.altars, level.core)}
    assert len(first) == BOARD_SIZE and all(len(row) == BOARD_SIZE for row in first)
    occupied = {(row, col) for row in range(BOARD_SIZE) for col in range(BOARD_SIZE)
                if first[row][col] is not None}
    assert occupied == set(expected)
    for pos, room in expected.items():
        tile = first[pos[0]][pos[1]]
        assert tile.kind == room.kind and tile.doors == room.doors
        assert tile.event_category is None and tile.event_outcome is None
        assert not tile.event_resolved
        assert tile.special_state == ("locked" if room.kind == "core" else None)
        assert tile.can_traverse() == (room.kind != "core")
    first[3][0].doors = (False, False, False, False)
    first[0][0] = first[3][0]
    assert second[3][0].doors == level.start.doors
    assert first[1][0] is None and second[0][0] is None


def test_config_is_immutable_and_snapshots_json_inputs(raw_level):
    before = deepcopy(raw_level)
    level = LevelConfig.from_mapping(raw_level)
    assert raw_level == before
    raw_level["objectives"]["start"]["pos"][0] = 2
    raw_level["objectives"]["start"]["doors"][0] = False
    raw_level["objectives"]["altars"].clear()
    assert level.start.pos == (3, 0) and level.start.doors[0]
    assert len(level.altars) == 2
    with pytest.raises(FrozenInstanceError):
        level.first_altar_supplies = 5
    with pytest.raises(FrozenInstanceError):
        level.start.pos = (2, 0)


def test_default_loader_is_independent_of_working_directory(tmp_path, monkeypatch):
    expected = load_level_config()
    monkeypatch.chdir(tmp_path)
    assert load_level_config() == expected


def test_custom_config_file_and_configurable_altar_count(raw_level, tmp_path):
    raw_level["objectives"]["altars"].pop()
    raw_level["objectives"]["first_altar_supplies"] = 0
    path = tmp_path / "level.json"
    path.write_text(json.dumps(raw_level), encoding="utf-8")
    one = load_level_config(path)
    assert len(one.altars) == 1 and one.first_altar_supplies == 0
    extra = SpecialRoom("altar_c", (0, 0), (False, True, True, False))
    three = replace(load_level_config(), altars=(*load_level_config().altars, extra))
    assert len(three.altars) == 3
    assert three.make_board()[0][0].kind == "altar_c"


@pytest.mark.parametrize("pos", [
    (-1, 0), (7, 0), (0, -1), (0, 7), (True, 0), (3.0, 0), ("3", 0),
    (3,), (3, 0, 1), [3, 0], None,
])
def test_special_room_rejects_invalid_positions(pos):
    with pytest.raises(ValueError, match="position"):
        SpecialRoom("altar_a", pos, (False, True, False, False))


@pytest.mark.parametrize("doors", [
    (), (True,), (True, False, False, False, False), [True, False, False, False],
    (1, False, False, False), (None, False, False, True), (False, False, False, False),
])
def test_special_room_rejects_invalid_doors_or_no_exits(doors):
    with pytest.raises(ValueError, match="doors"):
        SpecialRoom("altar_a", (3, 3), doors)


@pytest.mark.parametrize("pos,doors", [
    ((0, 2), (True, False, False, False)),
    ((3, 6), (False, True, False, False)),
    ((6, 3), (False, False, True, False)),
    ((4, 0), (False, False, False, True)),
])
def test_boundary_doors_are_rejected(pos, doors):
    with pytest.raises(ValueError, match="outside"):
        SpecialRoom("altar_a", pos, doors)


@pytest.mark.parametrize("kind", ["", "  ", "_comment", None, 5])
def test_special_room_rejects_invalid_ids(kind):
    with pytest.raises(ValueError, match="kind"):
        SpecialRoom(kind, (3, 3), (True, False, False, False))


@pytest.mark.parametrize("name,value", [
    ("start", None), ("core", None), ("altars", ()), ("altars", []),
    ("altars", (None,)), ("first_altar_supplies", True),
    ("first_altar_supplies", -1), ("first_altar_supplies", 1.5),
])
def test_level_rejects_invalid_roles_counts_and_reward(name, value):
    with pytest.raises(ValueError):
        replace(load_level_config(), **{name: value})


@pytest.mark.parametrize("role", ["start", "core"])
def test_start_and_core_keep_their_reserved_ids(role):
    level = load_level_config()
    with pytest.raises(ValueError, match="kind"):
        replace(level, **{role: replace(getattr(level, role), kind="other")})


def test_overlaps_and_duplicate_ids_are_rejected():
    level = load_level_config()
    overlapping = SpecialRoom("altar_c", level.start.pos, level.start.doors)
    with pytest.raises(ValueError, match="overlap"):
        replace(level, altars=(*level.altars, overlapping))
    duplicate = SpecialRoom(level.altars[0].kind, (0, 0), (False, True, True, False))
    with pytest.raises(ValueError, match="unique"):
        replace(level, altars=(*level.altars, duplicate))
    with pytest.raises(ValueError, match="unique"):
        replace(level, altars=(replace(level.altars[0], kind="core"),))


def test_adjacent_fixed_rooms_must_match_door_to_door_or_wall_to_wall():
    level = load_level_config()
    mismatch = SpecialRoom("altar_a", (3, 1), (False, True, False, False))
    with pytest.raises(ValueError, match="must match"):
        replace(level, altars=(mismatch,))
    joined = replace(mismatch, doors=(False, True, False, True))
    assert replace(level, altars=(joined,)).make_board()[3][1].kind == "altar_a"
    # A neighboring wall/wall pair is valid; both rooms still have another exit.
    start = SpecialRoom("start", (3, 0), (False, True, False, False))
    wall_neighbor = SpecialRoom("altar_a", (2, 0), (False, True, False, False))
    assert LevelConfig(start, (wall_neighbor,), level.core).start == start


def test_altars_cannot_require_crossing_the_locked_core_first():
    start = SpecialRoom("start", (3, 0), (False, True, False, False))
    core = SpecialRoom("core", (3, 1), (False, True, False, True))
    altar = SpecialRoom("altar_a", (3, 2), (False, False, False, True))
    with pytest.raises(ValueError, match="locked core"):
        LevelConfig(start, (altar,), core)


def test_potential_connectivity_respects_fixed_walls_around_empty_cells():
    # Every altar has an outward exit, but their walls enclose the core's
    # otherwise flexible empty-cell region. Do not accept arbitrary Manhattan paths.
    start = SpecialRoom("start", (3, 0), (True, True, True, False))
    altars = tuple(SpecialRoom(
        f"altar_{row}_{col}", (row, col), (row == 1, col == 5, row == 5, col == 1),
    ) for row in range(1, 6) for col in range(1, 6) if row in {1, 5} or col in {1, 5})
    core = SpecialRoom("core", (3, 3), (True, True, True, True))
    with pytest.raises(ValueError, match="core must be potentially reachable"):
        LevelConfig(start, altars, core)


@pytest.mark.parametrize("change", [
    "missing", "old_schema", "no_altars", "wrong_list", "missing_id", "bad_coord",
    "bad_boolean", "overlap", "wrong_board", "bool_board", "unknown_field",
])
def test_malformed_level_configuration_is_rejected(raw_level, change):
    objectives = raw_level["objectives"]
    if change == "missing":
        del raw_level["objectives"]
    elif change == "old_schema":
        objectives["start"] = [3, 0]
    elif change == "no_altars":
        objectives["altars"] = []
    elif change == "wrong_list":
        objectives["altars"] = {"altar_a": objectives["altars"][0]}
    elif change == "missing_id":
        del objectives["altars"][0]["id"]
    elif change == "bad_coord":
        objectives["start"]["pos"][0] = True
    elif change == "bad_boolean":
        objectives["start"]["doors"][0] = 1
    elif change == "overlap":
        objectives["altars"][0]["pos"] = [3, 0]
        objectives["altars"][0]["doors"] = [True, True, True, False]
    elif change == "wrong_board":
        raw_level["board"]["size"] = 8
    elif change == "bool_board":
        raw_level["board"]["size"] = True
    else:
        objectives["first_altar_suppliez"] = 2
    with pytest.raises(ValueError):
        LevelConfig.from_mapping(raw_level)
