"""Replay the documented winning example through public engine actions.

Run ``python -m engine.demo`` for a headless check and a human-readable action
list. The replay never installs rooms, overrides cards, or changes balancing.
"""

import json
from pathlib import Path

from engine.mvp import GameStatus, MvpSession


DEFAULT_DEMO_PATH = Path(__file__).resolve().parents[1] / "data" / "mvp_demo.json"


def replay_demo(path: str | Path = DEFAULT_DEMO_PATH) -> tuple[MvpSession, list[str]]:
    with Path(path).open(encoding="utf-8-sig") as source:
        demo = json.load(source)
    session = MvpSession(seed=demo["seed"])
    steps = []
    for number, action in enumerate(demo["actions"], 1):
        pos = tuple(action["pos"])
        label = f"{chr(ord('A') + pos[1])}{pos[0] + 1}"
        if action["action"] == "build":
            card, turns = action["card"], action["turns"]
            if not session.select_card(card - 1) or not session.rotate_selected(turns):
                raise ValueError(f"Demo step {number}: card selection or rotation failed")
            ok, reason = session.place(pos)
            instruction = f"Build {label}: card {card}, rotate R {turns} time(s)."
        elif action["action"] == "move":
            ok, reason = session.move(pos)
            instruction = f"Walk to {label}."
        else:
            raise ValueError(f"Demo step {number}: unknown action")
        if not ok:
            raise ValueError(f"Demo step {number} failed: {reason}")
        steps.append(instruction)
    if session.status != GameStatus.WON:
        raise ValueError("The recorded demonstration did not reach WON")
    return session, steps


def main() -> None:
    session, steps = replay_demo()
    print(f"Default-config winning example: seed {session.seed}")
    for index, step in enumerate(steps, 1):
        print(f"{index:2d}. {step}")
    print(f"{session.status.value}: {session.build_turn} builds; "
          f"HP {session.resources.hp}/{session.resources.hp_max}; "
          f"Supplies {session.resources.supplies}/{session.resources.supplies_max}; "
          f"altars {len(session.activated_altars)}/{len(session.level.altars)}")
    print("Only this recorded seed and action sequence are verified here.")


if __name__ == "__main__":
    main()
