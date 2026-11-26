"""Short guided practice using the normal build, movement and objective rules."""
from dataclasses import replace
from engine.cards import load_card_config
from engine.level import LevelConfig, SpecialRoom
from engine.mvp import MvpSession
from engine.events import EventConfig, EventOutcome


class TutorialSession(MvpSession):
    BUILD = (3, 1)
    PLAN = (3, 2)

    def __init__(self):
        config = load_card_config()
        room = next(r for r in config.room_types if r.kind == "straight")
        config = replace(config, room_types=(replace(room, event_weights=(("danger", 1), ("supply", 1))),))
        doors = (False, True, False, True)
        level = LevelConfig(
            SpecialRoom("start", (3, 0), (False, True, False, False)),
            (SpecialRoom("altar_a", (3, 3), doors), SpecialRoom("altar_b", (3, 4), doors)),
            SpecialRoom("core", (3, 5), (False, False, False, True)))
        events = EventConfig((
            ("danger", EventOutcome("A dart slips through a cracked mural.", hp_delta=-1, icon="dart")),
            ("supply", EventOutcome("Dry rations hang above the flood line.", supplies_delta=1, icon="supply")),
        ))
        super().__init__(seed=42, config=config, level=level, event_config=events)

    def restart(self):
        self.lesson = 0
        self.plan_created = False
        super().restart()
        self._lesson_cards("danger")

    def _lesson_cards(self, category):
        self.config = replace(self.config, room_types=tuple(
            replace(room, event_weights=((category, 1),)) for room in self.config.room_types))
        self.draw_result = replace(self.draw_result, cards=tuple(
            replace(card, event_category=category) for card in self.draw_result.cards))

    @property
    def narration(self):
        if self.status == "LOST":
            return "The guard depleted your HP. Press N to restart the tutorial."
        if self.lesson == 4 and self.current_event is not None and self.current_event.category == "guard":
            return "The guard hit you for 1 HP and returned to Start. Its arrow marks danger; move toward the next altar or core."
        if self.lesson == 0:
            return "Choose card 1. The highlighted room shows your next goal."
        if self.lesson == 1:
            return "Card selected. Rotate with R, then build B4 to discover a danger event."
        if self.lesson == 2:
            return "Dart trap: you lost 1 HP. Walk back to A4; this trap will not trigger again."
        if self.lesson == 3:
            if self.plan_created and self.player_pos == self.BUILD:
                return "You reached the entrance safely. Press Enter to build the supply room."
            return ("Plan ready. Press G to walk to its entrance, then Enter to build."
                    if self.plan_created else "Backtracking was free. Select 1, rotate with R and plan C4 for supplies.")
        if self.lesson == 5:
            return "Both altars are active. You entered the core and won!"
        if not self.activated_altars:
            return "Supplies gained! Connecting the altar woke the guard. Avoid its arrow and walk right to activate the altar."
        if len(self.activated_altars) == 1:
            return "First altar activated. The guard advances whenever you walk or build. Walk right to the second altar."
        return "Both altars are active and the core is unlocked. Walk right into the core."

    def select_card(self, index):
        if self.lesson not in (0, 1, 3) or index != 0:
            return False
        ok = super().select_card(index)
        if ok and self.lesson == 0:
            self.lesson = 1
        return ok

    def rotate_selected(self, times=1):
        if self.lesson not in (1, 3):
            return False
        return super().rotate_selected(times)

    @property
    def lesson_target(self):
        if self.lesson == 4:
            if self.player_pos in (self.level.start.pos, self.BUILD):
                return self.PLAN
            if "altar_a" not in self.activated_altars:
                return self.level.altars[0].pos
            if "altar_b" not in self.activated_altars:
                return self.level.altars[1].pos
            return self.level.core.pos
        return {1: self.BUILD, 2: self.level.start.pos, 3: self.PLAN}.get(self.lesson)

    def preview(self, pos):
        if self.lesson not in (1, 3) or pos != self.lesson_target:
            return False, "tutorial_step"
        if self.lesson == 3 and not self.plan_created:
            return False, "tutorial_step"
        return super().preview(pos)

    def geometry_preview(self, pos):
        if self.lesson not in (1, 3) or pos != self.lesson_target:
            return False, "tutorial_step"
        return super().geometry_preview(pos)

    def planning_cells(self):
        return super().planning_cells() & {self.lesson_target} if self.lesson in (1, 3) else set()

    def legal_cells(self):
        return super().legal_cells() & {self.BUILD} if self.lesson == 1 else set()

    def mark_plan(self, pos):
        if self.lesson == 3 and pos == self.PLAN:
            self.plan_created = True

    def place(self, pos):
        result = super().place(pos)
        if result[0]:
            self.lesson = 2 if self.lesson == 1 else 4
            self._lesson_cards("supply")
        return result

    def movement_preview(self, pos):
        if self.lesson < 2 or self.lesson >= 5 or (self.lesson == 2 and pos != self.lesson_target):
            return False, "tutorial_step"
        return super().movement_preview(pos)

    def move(self, pos):
        result = super().move(pos)
        if result[0]:
            if self.lesson == 2:
                self.lesson = 3
            elif self.status == "WON":
                self.lesson = 5
        return result

    def tool_budget(self, name):
        return False, "tutorial_step"

    def medkit_preview(self):
        return False, "tutorial_step"
