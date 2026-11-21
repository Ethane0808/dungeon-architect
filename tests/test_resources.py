"""Resource validation, configured bounds, recovery and zero-HP safety."""

from dataclasses import FrozenInstanceError

import pytest

from engine.resources import Resources, load_resources


def test_provisional_initial_resources_are_loaded_from_existing_config():
    assert load_resources() == Resources(hp=5, hp_max=5, supplies=2, supplies_max=5)


def test_damage_and_recovery_return_new_bounded_states():
    initial = Resources(4, 6, 2, 5)
    damaged = initial.apply(hp_delta=-2)
    assert damaged.hp == 2
    assert initial.hp == 4
    assert damaged.apply(hp_delta=100).hp == 6
    depleted = damaged.apply(hp_delta=-100)
    assert depleted.hp == 0 and depleted.hp_depleted
    assert depleted.apply(hp_delta=-1).hp == 0
    assert depleted.apply(hp_delta=1).hp == 1
    with pytest.raises(FrozenInstanceError):
        initial.hp = -1


def test_supplies_obey_both_configured_bounds():
    initial = Resources(6, 6, 3, supplies_max=5, supplies_min=1)
    assert initial.apply(supplies_delta=1).supplies == 4
    assert initial.apply(supplies_delta=100).supplies == 5
    assert initial.apply(supplies_delta=-100).supplies == 1
    assert initial.supplies == 3


def test_supplies_can_have_no_upper_limit():
    initial = Resources(6, 6, 0)
    assert initial.apply(supplies_delta=10**20).supplies == 10**20
    assert initial.apply(supplies_delta=-1).supplies == 0


@pytest.mark.parametrize("overrides", [
    {"hp": -1}, {"hp": 7}, {"hp_max": 0}, {"hp_max": -1},
    {"supplies": -1}, {"supplies": 6}, {"supplies_min": -1},
    {"supplies_min": 3}, {"supplies_max": -1},
    {"hp": True}, {"hp_max": 6.0}, {"supplies": float("nan")},
    {"supplies_max": True}, {"supplies_min": "0"},
])
def test_invalid_initial_resources_are_rejected(overrides):
    values = dict(hp=6, hp_max=6, supplies=2, supplies_max=5)
    values.update(overrides)
    with pytest.raises(ValueError):
        Resources(**values)


@pytest.mark.parametrize("value", [True, False, 1.5, float("inf"), float("nan"), "1", None])
@pytest.mark.parametrize("field", ["hp_delta", "supplies_delta"])
def test_non_integer_changes_are_rejected_without_mutation(field, value):
    initial = Resources(6, 6, 2, 5)
    with pytest.raises(ValueError):
        initial.apply(**{field: value})
    assert initial == Resources(6, 6, 2, 5)


def test_player_config_supports_optional_supply_bounds():
    config = {"player": {"hp_initial": 3, "hp_max": 8, "supplies_initial": 1}}
    assert Resources.from_mapping(config) == Resources(3, 8, 1)
    config["player"].update(supplies_min=1, supplies_max=4)
    assert Resources.from_mapping(config) == Resources(3, 8, 1, 4, 1)


@pytest.mark.parametrize("data", [{}, {"player": {}}, {"player": None}])
def test_missing_player_config_is_rejected(data):
    with pytest.raises(ValueError, match="configuration"):
        Resources.from_mapping(data)
