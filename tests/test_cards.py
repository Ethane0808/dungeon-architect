"""Phase 2 regression tests: DRAW-01/02/03, ROT-02 and seeded previews."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from itertools import product
import json
import os
from pathlib import Path
from random import Random
import random
import subprocess
import sys

import pytest

from engine.cards import (
    DEFAULT_CONFIG_PATH, CardConfig, RoomType, draw_cards, enumerate_legal_placements,
    load_card_config, unique_rotations,
)
from engine.directions import DIRECTIONS, OPPOSITE, neighbor_pos, rotate_doors
from engine.models import BOARD_SIZE, Tile, make_empty_board
from engine.placement import can_place, reachable_rooms


@pytest.fixture(scope="module")
def config():
    return load_card_config()


@pytest.fixture
def raw_config():
    return json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def open_board():
    board = make_empty_board()
    board[3][3] = Tile("start", (True, True, True, True))
    return board


def constrained_board(doors):
    """Force the empty center's four edges, with only its west room reachable."""
    board = make_empty_board()
    for direction in DIRECTIONS:
        row, col = neighbor_pos(3, 3, direction)
        neighbor_doors = [False] * 4
        neighbor_doors[OPPOSITE[direction]] = doors[direction]
        board[row][col] = Tile("room", tuple(neighbor_doors))
    return board


def assert_hand_is_legal(result, board, start):
    reachable = reachable_rooms(board, start)
    assert result.status == "ready"
    assert len(result.cards) == 3
    actual_indices = []
    for index, card in enumerate(result.cards):
        if any(can_place(Tile(card.kind, doors), (row, col), board, reachable)[0]
               for row in range(BOARD_SIZE) for col in range(BOARD_SIZE)
               for _, doors in unique_rotations(card.doors)):
            actual_indices.append(index)
    assert actual_indices
    assert result.legal_card_indices == tuple(actual_indices)


def test_default_config_loads_existing_provisional_settings(config):
    rooms = {room.kind: room for room in config.room_types}
    assert set(rooms) == {"dead_end", "straight", "corner", "t_junction", "cross"}
    assert rooms["straight"].weight == 3
    assert dict(rooms["cross"].event_weights) == {"supply": 3, "danger": 3, "neutral": 4}
    assert config.boost_second_legal_weight == 2


def test_default_path_is_independent_of_working_directory(config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_card_config() == config


def test_custom_config_path_and_input_snapshot(raw_config, tmp_path):
    before = deepcopy(raw_config)
    path = tmp_path / "cards.json"
    path.write_text(json.dumps(raw_config), encoding="utf-8")
    settings = load_card_config(path)
    assert settings == CardConfig.from_mapping(raw_config)
    assert raw_config == before
    raw_config["room_types"]["cross"]["doors"][0] = False
    assert next(room for room in settings.room_types if room.kind == "cross").doors[0] is True


@pytest.mark.parametrize("kind,count", [
    ("dead_end", 4), ("straight", 2), ("corner", 4), ("t_junction", 4), ("cross", 1),
])
def test_equivalent_rotations_are_deduplicated(config, kind, count):
    room = next(room for room in config.room_types if room.kind == kind)
    rotations = unique_rotations(room.doors)
    assert len(rotations) == count
    assert len({doors for _, doors in rotations}) == count
    assert {doors for _, doors in rotations} == {rotate_doors(room.doors, turns) for turns in range(4)}
    assert all(rotate_doors(room.doors, turns) == doors for turns, doors in rotations)


def test_all_reachable_frontiers_and_shapes_are_enumerated(config, open_board):
    legal = enumerate_legal_placements(open_board, (3, 3), config)
    assert {option.pos for option in legal} == {(2, 3), (3, 4), (4, 3), (3, 2)}
    assert len(legal) == 32
    assert len({(option.pos, option.kind, option.doors) for option in legal}) == len(legal)
    assert list(legal) == sorted(legal, key=lambda option: (option.pos, option.kind, option.rotation))


@pytest.mark.parametrize("seed", [0, 17, 86])
def test_enumeration_matches_full_board_search_during_growth(config, seed):
    board = make_empty_board()
    board[3][3] = Tile("start", (True, True, True, True))
    rng = Random(seed)
    for _ in range(6):
        actual = enumerate_legal_placements(board, (3, 3), config)
        reachable = reachable_rooms(board, (3, 3))
        expected = set()
        # Full-board oracle deliberately avoids frontier enumeration.
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                for room in config.room_types:
                    for turns in range(4):
                        doors = rotate_doors(room.doors, turns)
                        if can_place(Tile(room.kind, doors), (row, col), board, reachable)[0]:
                            expected.add(((row, col), room.kind, doors))
        assert {(option.pos, option.kind, option.doors) for option in actual} == expected
        assert len(actual) == len(expected)
        result = draw_cards(board, (3, 3), rng=rng, config=config)
        if not actual:
            assert result.status == "blocked"
            break
        assert_hand_is_legal(result, board, (3, 3))
        option = rng.choice(actual)
        board[option.pos[0]][option.pos[1]] = Tile(option.kind, option.doors)


def test_draw_02_frontier_can_be_far_from_player(config):
    board = make_empty_board()
    board[3][3] = Tile("start", (False, True, False, False))
    board[3][4] = Tile("straight", (False, True, False, True))
    result = draw_cards(board, (3, 3), rng=Random(9), config=config)
    assert {option.pos for option in result.legal_placements} == {(3, 5)}
    assert_hand_is_legal(result, board, (3, 3))


def test_unreachable_islands_do_not_produce_options(config):
    board = make_empty_board()
    board[1][1] = Tile("start", (False, True, False, False))
    board[5][5] = Tile("room", (True, True, True, True))
    legal = enumerate_legal_placements(board, (1, 1), config)
    assert {option.pos for option in legal} == {(1, 2)}


@pytest.mark.parametrize("source", DIRECTIONS)
def test_all_four_neighbors_constrain_legality(config, source):
    doors = rotate_doors((False, True, False, True), source)
    board = constrained_board(doors)
    start = neighbor_pos(3, 3, 0 if doors[0] else 1)
    legal = enumerate_legal_placements(board, start, config)
    assert len(legal) == 1
    assert legal[0].kind == "straight"
    assert legal[0].pos == (3, 3)
    assert legal[0].doors == doors


@pytest.mark.parametrize("pos,source", [
    ((0, 0), 1), ((0, 6), 2), ((6, 6), 3), ((6, 0), 0),
    ((0, 3), 2), ((6, 3), 0), ((3, 0), 1), ((3, 6), 3),
])
def test_corner_and_edge_enumeration(config, pos, source):
    board = make_empty_board()
    row, col = neighbor_pos(*pos, source)
    doors = [False] * 4
    doors[OPPOSITE[source]] = True
    board[row][col] = Tile("start", tuple(doors))
    legal = enumerate_legal_placements(board, (row, col), config)
    assert legal and all(option.pos == pos for option in legal)
    for option in legal:
        for direction, has_door in enumerate(option.doors):
            nr, nc = neighbor_pos(*option.pos, direction)
            assert not has_door or (0 <= nr < BOARD_SIZE and 0 <= nc < BOARD_SIZE)
    assert_hand_is_legal(draw_cards(board, (row, col), rng=Random(0), config=config), board, (row, col))


def test_locked_core_blocks_remote_frontier_until_unlocked(config):
    board = make_empty_board()
    board[3][3] = Tile("start", (False, True, False, False))
    core = Tile("core", (False, True, False, True), special_state="locked")
    board[3][4] = core
    assert draw_cards(board, (3, 3), rng=Random(2), config=config).status == "blocked"
    core.special_state = "unlocked"
    result = draw_cards(board, (3, 3), rng=Random(2), config=config)
    assert {option.pos for option in result.legal_placements} == {(3, 5)}


def test_can_match_locked_core_geometry_without_entering_it(config):
    board = make_empty_board()
    board[3][2] = Tile("start", (False, True, False, False))
    board[3][4] = Tile("core", (False, False, False, True), special_state="locked")
    legal = enumerate_legal_placements(board, (3, 2), config)
    assert legal and all(option.doors[1] and option.doors[3] for option in legal)


@pytest.mark.parametrize("blocked", [(3, 3), (3, 4)])
def test_extra_locks_are_forwarded(config, blocked):
    board = make_empty_board()
    board[3][3] = Tile("start", (False, True, False, False))
    board[3][4] = Tile("room", (False, True, False, True))
    assert enumerate_legal_placements(board, (3, 3), config, {blocked}) == ()
    assert draw_cards(board, (3, 3), rng=Random(0), config=config,
                      locked_specials={blocked}).status == "blocked"


@pytest.mark.parametrize("seed", range(25))
def test_draw_01_single_legal_shape_is_always_in_hand(config, seed):
    board = constrained_board((True, True, True, True))
    result = draw_cards(board, (3, 2), rng=Random(seed), config=config)
    assert {option.kind for option in result.legal_placements} == {"cross"}
    assert_hand_is_legal(result, board, (3, 2))


def test_zero_weight_legal_shape_still_receives_protection(config):
    settings = replace(config, room_types=tuple(
        replace(room, weight=0) if room.kind == "cross" else room for room in config.room_types
    ))
    board = constrained_board((True, True, True, True))
    for seed in range(10):
        result = draw_cards(board, (3, 2), rng=Random(seed), config=settings)
        assert sum(card.kind == "cross" for card in result.cards) == 1
        assert_hand_is_legal(result, board, (3, 2))


@pytest.mark.parametrize("north,east,south", list(product((False, True), repeat=3)))
def test_protection_covers_every_forced_shape(config, north, east, south):
    doors = (north, east, south, True)
    board = constrained_board(doors)
    legal = enumerate_legal_placements(board, (3, 2), config)
    assert len(legal) == 1 and legal[0].doors == doors
    for seed in range(5):
        assert_hand_is_legal(draw_cards(board, (3, 2), rng=Random(seed), config=config), board, (3, 2))


def test_duplicates_are_allowed_and_second_option_is_soft(config, open_board):
    hands = [draw_cards(open_board, (3, 3), rng=Random(seed), config=config).cards for seed in range(100)]
    assert any(len({card.kind for card in cards}) < 3 for cards in hands)
    assert any(len({card.kind for card in cards}) == 1 for cards in hands)


def test_boost_prefers_distinct_legal_options(config, open_board):
    def diversity(boost):
        rng = Random(1234)
        settings = replace(config, boost_second_legal_weight=boost)
        return sum(len({card.kind for card in draw_cards(
            open_board, (3, 3), rng=rng, config=settings,
        ).cards}) for _ in range(200))
    assert diversity(4) > diversity(1)


@pytest.mark.parametrize("scenario", ["empty", "closed", "full", "no_shape", "invalid_start"])
def test_draw_03_blocked_is_explicit_and_does_not_consume_rng(config, scenario):
    board = make_empty_board()
    start = (3, 3)
    if scenario == "closed":
        board[3][3] = Tile("start", (False, False, False, False))
    elif scenario == "full":
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                board[row][col] = Tile("room", (False, False, False, False))
    elif scenario == "no_shape":
        # There is a reachable frontier at (0,0), but a cross cannot fit there.
        board[0][1] = Tile("start", (False, False, False, True))
        start = (0, 1)
        config = replace(config, room_types=tuple(room for room in config.room_types if room.kind == "cross"))
    elif scenario == "invalid_start":
        start = (-1, 3)
    rng = Random(55)
    before = deepcopy(board), rng.getstate()
    result = draw_cards(board, start, rng=rng, config=config)
    assert result.status == "blocked"
    assert result.cards == result.legal_placements == result.legal_card_indices == ()
    assert (board, rng.getstate()) == before


def test_blocked_can_recover_after_external_board_change(config):
    board = make_empty_board()
    board[3][3] = Tile("start", (False, False, False, False))
    rng = Random(7)
    blocked = draw_cards(board, (3, 3), rng=rng, config=config)
    assert blocked.status == "blocked"
    board[3][3].doors = (False, True, False, False)
    assert_hand_is_legal(draw_cards(board, (3, 3), rng=rng, config=config), board, (3, 3))
    assert blocked.status == "blocked" and blocked.cards == ()


def test_seeded_streams_are_reproducible(config, open_board):
    left, right = Random(123), Random(123)
    left_hands = [draw_cards(open_board, (3, 3), rng=left, config=config) for _ in range(5)]
    right_hands = [draw_cards(open_board, (3, 3), rng=right, config=config) for _ in range(5)]
    assert left_hands == right_hands
    assert left.getstate() == right.getstate()
    assert len({hand.cards for hand in left_hands}) > 1


def test_configuration_key_order_does_not_change_seeded_result(raw_config, open_board):
    reordered = deepcopy(raw_config)
    reordered["room_types"] = dict(reversed(list(reordered["room_types"].items())))
    reordered["events"]["categories"].reverse()
    assert draw_cards(open_board, (3, 3), rng=Random(123), config=CardConfig.from_mapping(raw_config)) == draw_cards(
        open_board, (3, 3), rng=Random(123), config=CardConfig.from_mapping(reordered),
    )


def test_pure_python_and_hash_seed_independent():
    script = """
import sys
sys.modules['pygame'] = None
from dataclasses import asdict
import json
from random import Random
from engine.cards import draw_cards
from engine.models import Tile, make_empty_board
board = make_empty_board()
board[3][3] = Tile('start', (True, True, True, True))
print(json.dumps(asdict(draw_cards(board, (3,3), rng=Random(42))), sort_keys=True))
"""
    outputs = []
    for seed in (1, 42):
        result = subprocess.run(
            [sys.executable, "-B", "-c", script],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "PYTHONHASHSEED": str(seed)},
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, result.stderr
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]


def test_preview_categories_follow_config_without_resolving_events(raw_config, open_board):
    raw_config["events"]["weights_by_kind"]["cross"] = {"danger": 1, "supply": 0, "neutral": 0}
    raw_config["events"]["weights_by_kind"]["dead_end"] = {"danger": 0, "supply": 1, "neutral": 0}
    settings = CardConfig.from_mapping(raw_config)
    settings = replace(settings, room_types=tuple(room for room in settings.room_types if room.kind in {"cross", "dead_end"}))
    seen = set()
    for seed in range(20):
        for card in draw_cards(open_board, (3, 3), rng=Random(seed), config=settings).cards:
            assert card.event_category == {"cross": "danger", "dead_end": "supply"}[card.kind]
            assert card.rotated().event_category == card.event_category
            assert card.rotated(4) == card
            seen.add(card.kind)
    assert seen == {"cross", "dead_end"}


def test_generation_and_preview_do_not_mutate_board_config_or_global_rng(config, open_board):
    open_board[3][3].event_outcome = {"hp": -1}
    open_board[3][3].event_resolved = True
    before = deepcopy(open_board), deepcopy(config), random.getstate()
    enumerate_legal_placements(open_board, (3, 3), config)
    result = draw_cards(open_board, (3, 3), rng=Random(1), config=config)
    card = result.cards[0]
    preview = card.rotated()
    assert preview.doors == rotate_doors(card.doors)
    assert (open_board, config, random.getstate()) == before
    with pytest.raises(FrozenInstanceError):
        card.event_category = "changed"
    with pytest.raises(FrozenInstanceError):
        result.status = "blocked"


@pytest.mark.parametrize("section,key,value", [
    ("board", "size", 8), ("board", "size", 7.0),
    ("draw", "hand_size", 2), ("draw", "guarantee_one_legal", False),
    ("draw", "boost_second_legal_weight", 0.5),
    ("draw", "boost_second_legal_weight", float("inf")),
    ("draw", "boost_second_legal_weight", float("nan")),
    ("draw", "boost_second_legal_weight", True),
    ("events", "categories", []), ("events", "categories", ["supply", "supply"]),
    ("events", "categories", ["supply", "unknown"]),
])
def test_invalid_settings_are_rejected(raw_config, section, key, value):
    raw_config[section][key] = value
    with pytest.raises(ValueError):
        CardConfig.from_mapping(raw_config)


@pytest.mark.parametrize("doors", [[True] * 3, [1, 0, 0, 0], [False] * 4, "NESW"])
def test_invalid_room_geometry_is_rejected(raw_config, doors):
    raw_config["room_types"]["cross"]["doors"] = doors
    with pytest.raises(ValueError):
        CardConfig.from_mapping(raw_config)


@pytest.mark.parametrize("weight", [-1, float("inf"), float("nan"), "1", True])
@pytest.mark.parametrize("target", ["room", "preview"])
def test_invalid_weights_are_rejected(raw_config, weight, target):
    if target == "room":
        raw_config["room_types"]["cross"]["weight"] = weight
    else:
        raw_config["events"]["weights_by_kind"]["cross"]["supply"] = weight
    with pytest.raises(ValueError):
        CardConfig.from_mapping(raw_config)


@pytest.mark.parametrize("scenario", ["missing", "empty", "zero_rooms", "zero_events", "special"])
def test_incomplete_or_unusable_config_is_rejected(raw_config, scenario):
    if scenario == "missing":
        del raw_config["events"]["weights_by_kind"]["cross"]
    elif scenario == "empty":
        raw_config["room_types"] = {}
    elif scenario == "zero_rooms":
        for kind, room in raw_config["room_types"].items():
            if not kind.startswith("_"):
                room["weight"] = 0
    elif scenario == "zero_events":
        raw_config["events"]["weights_by_kind"]["cross"] = {"supply": 0, "danger": 0, "neutral": 0}
    else:
        raw_config["room_types"]["core"] = raw_config["room_types"]["cross"]
        raw_config["events"]["weights_by_kind"]["core"] = raw_config["events"]["weights_by_kind"]["cross"]
    with pytest.raises(ValueError):
        CardConfig.from_mapping(raw_config)


def test_large_finite_weights_do_not_overflow(config, open_board):
    settings = replace(config, boost_second_legal_weight=1e308, room_types=tuple(
        replace(room, weight=1e308, event_weights=(("neutral", 1e308),)) for room in config.room_types
    ))
    assert_hand_is_legal(draw_cards(open_board, (3, 3), rng=Random(9), config=settings), open_board, (3, 3))


class RecordingRoomRandom(Random):
    """Expose sampling weights and keep the first shape selected for these tests."""

    def __init__(self):
        super().__init__(0)
        self.room_weights = []

    def choices(self, population, weights=None, *, cum_weights=None, k=1):
        if isinstance(population[0], RoomType):
            self.room_weights.append(dict(zip((room.kind for room in population), weights)))
            return [population[0]] * k
        return super().choices(population, weights, cum_weights=cum_weights, k=k)


@pytest.mark.parametrize("heavy,tiny,boost", [
    (1e124, 1e-200, 1e308),  # Review reproduction: divide-first loses the boost.
    (1e308, 1e-308, 1e308),
    (1e308, 1e308, 1e308),  # Multiplying first would overflow.
    (1.0, 5e-324, 1e308),   # Smallest positive float can regain representable weight.
    (10**308, 10**308, 10**308),
    (3.0, 2.0, 2.0),
])
def test_diversity_boost_preserves_adjusted_weight_ratios(open_board, heavy, tiny, boost):
    settings = CardConfig((
        RoomType("a_heavy", (True, False, False, False), heavy, (("neutral", 1),)),
        RoomType("b_distinct", (True, True, False, False), tiny, (("neutral", 1),)),
    ), boost_second_legal_weight=boost)
    rng = RecordingRoomRandom()
    result = draw_cards(open_board, (3, 3), rng=rng, config=settings)

    # Decimal provides an independent oracle without intermediate float overflow.
    adjusted = {"a_heavy": Decimal(heavy), "b_distinct": Decimal(tiny) * Decimal(boost)}
    maximum = max(adjusted.values())
    expected = {kind: float(weight / maximum) for kind, weight in adjusted.items()}
    for actual in rng.room_weights[1:]:
        assert actual == pytest.approx(expected, rel=1e-12, abs=0)
        assert actual["b_distinct"] > 0
    assert_hand_is_legal(result, open_board, (3, 3))


def test_large_diversity_boost_keeps_zero_weight_at_zero(open_board):
    settings = CardConfig((
        RoomType("a_positive", (True, False, False, False), 1, (("neutral", 1),)),
        RoomType("b_zero", (True, True, False, False), 0, (("neutral", 1),)),
    ), boost_second_legal_weight=1e308)
    rng = RecordingRoomRandom()
    draw_cards(open_board, (3, 3), rng=rng, config=settings)
    assert len(rng.room_weights) == 3
    assert all(weights == {"a_positive": 1.0, "b_zero": 0.0} for weights in rng.room_weights)


@pytest.mark.parametrize("weights", [[("neutral", 1)], (["neutral", 1],), (("neutral", 1, 2),)])
def test_direct_config_cannot_contain_mutable_or_malformed_weight_pairs(config, weights):
    with pytest.raises(ValueError):
        replace(config.room_types[0], event_weights=weights)


def test_direct_config_rejects_duplicate_room_kinds(config):
    with pytest.raises(ValueError):
        CardConfig((config.room_types[0], config.room_types[0]))


@pytest.mark.parametrize("operation", [enumerate_legal_placements, draw_cards])
def test_malformed_board_preserves_phase_1_validation(config, operation):
    kwargs = {"rng": Random(0)} if operation is draw_cards else {}
    with pytest.raises(ValueError, match="7"):
        operation([[None] * 3 for _ in range(3)], (1, 1), config=config, **kwargs)
