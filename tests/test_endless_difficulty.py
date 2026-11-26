import json
from dataclasses import replace

import pytest

from engine.endless import DIFFICULTY_PATH, DifficultyError, EndlessRun
from engine.mvp import GameStatus, MvpSession
from engine.level import load_level_config
from tests.test_mvp import cross_config


def test_floor_variants_cycle_without_accumulating_tool_restrictions():
    expedition = MvpSession(159)
    run = EndlessRun(expedition)
    expected = [(1, 11, "random", 2, 3), (3, 9, "random", 2, 3),
                (5, 8, "near_start", 2, 3), (6, 8, "far_from_start", 2, 3),
                (7, 7, "near_start", 1, 3), (8, 7, "far_from_start", 2, 2),
                (9, 7, "near_start", 1, 3)]
    for floor, guard, well, chisels, seals in expected:
        while run.floor < floor:
            run.session.status = GameStatus.WON
            assert run.advance()
        s = run.session
        assert (s.level.guard_build_limit, s.level.spring_position) == (guard, well)
        assert (s.tools.emergency_chisel.max_uses_per_game, s.tools.door_seal.max_uses_per_game) == (chisels, seals)
        reachable = s.level.potential_positions(s.board, core_locked=True)
        assert all(a.pos in reachable for a in s.level.altars)
        assert s.level.core.pos in s.level.potential_positions(s.board, core_locked=False)


def test_well_placement_uses_nearer_or_farther_cells_on_the_same_terrain():
    level = replace(load_level_config(), rubble_count=4)
    for seed in range(32):
        distances = []
        for position in ("near_start", "far_from_start"):
            board = replace(level, spring_position=position).make_board(seed)
            wells = [(r, c) for r, row in enumerate(board) for c, tile in enumerate(row)
                     if tile and tile.kind == "spring"]
            (r, c), = wells
            distances.append(abs(r - level.start.pos[0]) + abs(c - level.start.pos[1]))
            assert sum(tile.kind == "rubble" for row in board for tile in row if tile) == 4
            assert level.core.pos in level.potential_positions(board, core_locked=False)
        assert distances[0] < distances[1]


def test_danger_chances_increase_on_every_floor_without_changing_base_settings():
    base = MvpSession(42)
    run = EndlessRun(base)
    assert run.session.config == base.config
    for depth in range(1, 12):
        previous = run.session
        previous.status = GameStatus.WON
        assert run.advance()
        for initial, old, new in zip(base.config.room_types, previous.config.room_types, run.session.config.room_types):
            weights = dict(initial.event_weights)
            weights["danger"] *= 1 + depth / (depth + 5)
            assert dict(new.event_weights) == pytest.approx(weights)
            old_weights = dict(old.event_weights)
            assert weights["danger"] / sum(weights.values()) > old_weights["danger"] / sum(old_weights.values())
    run.restart()
    assert run.session.config == base.config


def test_settings_reload_and_can_be_repaired_without_losing_a_floor(tmp_path):
    path = tmp_path / "difficulty.json"
    def save(limit):
        path.write_text(json.dumps({"tiers": [{"from_floor": 1, "guard_build_limit": limit,
                                               "variants": [{"chisel_uses": 0}]}]}), encoding="utf-8")
    save(10)
    run = EndlessRun(MvpSession(42), path)
    first = run.session
    first.status = GameStatus.WON
    save(0)
    with pytest.raises(DifficultyError):
        run.advance()
    assert run.session is first and run.floor == 1
    save(4)
    assert run.advance()
    assert first.level.guard_build_limit == 10 and run.session.level.guard_build_limit == 4
    assert run.session.tools.emergency_chisel.max_uses_per_game == 0


def test_floor_one_well_and_configured_special_encounter(tmp_path):
    settings = json.loads(DIFFICULTY_PATH.read_text(encoding="utf-8"))
    settings["events"].update(bell_percent=100, special_weights={"monster": 1}, danger_bonus_percent=0)
    settings["tiers"][0]["variants"] = [{"spring_count": 0, "rubble_count": 0},
                                         {"spring_count": 1, "rubble_count": 0}]
    path = tmp_path / "difficulty.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    run = EndlessRun(MvpSession(159, cross_config("relic")), path)
    for kind in ("spring", "bell"):
        kinds = [tile.kind for row in run.session.board for tile in row if tile]
        assert [item for item in kinds if item in ("spring", "bell")] == [kind]
        assert run.session.select_card(0) and run.session.place((3, 1))[0]
        assert run.session.encounter == "monster"
        assert run.session.config == run.template.config
        run.session.status = GameStatus.WON
        assert run.advance()
