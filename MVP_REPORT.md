# Phase 5 MVP delivery

**MVP FUNCTIONAL — MANUAL VERIFICATION REQUIRED**

Implemented on 2026-11-12 and independently reviewed on 2026-11-13 using Python 3.14.7. Work is on
`feature/mvp-completion`, created from `ac70604`, the latest `main` containing
merged Phase 4 PR #4. The starting working tree was clean. No Phase 5 commit,
push or merge was performed during implementation or review. Publication was
separately authorized by the user after review; desktop acceptance remains pending.

Final review fixed two P2 UI feedback defects and verified **563 passing tests**,
the recorded win, and bounded checks across 51 seeds. No P0/P1 defect was found.
See [MVP_REVIEW_REPORT.md](MVP_REVIEW_REPORT.md) for evidence, limits and the
remaining physical-desktop acceptance checklist.

## Implementation summary

The game now runs from a visible fixed layout through construction, exploration,
events, resources, spatial recovery tools, altar activation, core unlock, victory
or defeat, and restart. `main.py` launches `MvpSession`, an extension of the
existing `BuildSession`; the Phase 4 controller and all its existing tests remain
available without changed semantics.

The engine validates special-room positions and doors, reserves those cells,
requires actual altar entry, and prevents core traversal before every configured
altar is activated. The existing first-entry ordinary events, bounded resources,
strict matching and protected draws are reused. Movement remains free and does
not reroll an existing hand.

Door Seal modifies one door on the selected card before placement validation.
Emergency Chisel opens both sides of an existing wall-to-wall room boundary.
Costs, usage counts, geometry, objective effects and draw refresh are committed
together only after the entire operation succeeds. Terminal states reject
further gameplay actions and retain restart/quit controls.

## New and modified files

| Files | Responsibility |
|---|---|
| New `engine/level.py` | Immutable level definitions and initial geometry/potential-route validation. |
| New `engine/mvp.py` | Objective progression, milestone, atomic candidate states, tools and PLAYING/WON/LOST. |
| New `engine/tools.py` | Tool configuration and pure, validated geometry transformations. |
| New `engine/demo.py`, `data/mvp_demo.json` | Recorded public-action replay of the default-config winning run. |
| `data/prototype_config.json` | v0.10 objective positions/doors schema; unchanged resource values, weights and tool costs. |
| `main.py` | Launch the MVP controller with the existing seed option. |
| `ui/app.py`, `ui/screens.py` | Tool controls, objective checklist, fixed-room markers, lock state and terminal overlays. |
| New `tests/test_level.py`, `tests/test_tools.py` | Configuration, geometry, locks, metadata preservation and pure-tool failures. |
| New `tests/test_mvp.py` | Objectives, costs/limits, terminal rules, restart, blocked recovery and full-state rollback. |
| New `tests/test_mvp_demo.py` | Default winning replay, deterministic restart, headless command and Pygame-input completion. |
| New `tests/test_mvp_ui.py` | Tool inputs, costs, special-room display, terminal input blocking and restart. |
| `README.md`, `GAME_DESIGN.md`, `DECISIONS.md`, `TASKS.md` | Current gameplay, provisional rules, controls, progress and readiness. |
| `TECH_SPEC.md`, `TEST_PLAN.md`, new `MVP_REPORT.md` | Architecture/APIs, verification, replay and manual acceptance instructions. |

## Complete gameplay workflow

1. Start with a validated 7×7 fixed layout and three protected room cards.
2. Select a card and rotation; optionally select a door to seal.
3. Choose a legal empty frontier connected to the reachable dungeon.
4. Validate every existing neighbor, the map boundary, tool cost and usage limit.
5. Build, automatically enter, resolve its ordinary event once, update bounded
   HP/Supplies, and prepare the next hand atomically.
6. Walk through matching unlocked doors, preserving the hand, rotations and turn.
7. Enter each altar. The first activated altar grants its one-time configured
   milestone; every altar activates at most once.
8. Once all altars activate, unlock the core. Enter it through a valid doorway
   to reach WON. HP reaching zero instead reaches LOST.
9. Terminal overlays block further gameplay and offer restart. Restart restores
   level, cards, RNG, resources, event state, objectives and tool uses.

When no normal placement exists, the run stays PLAYING. Walking, objectives,
affordable recovery tools and restart remain available. Chisel may reconnect an
isolated room and recover a protected hand. A tool that changes connectivity
does not itself enter the room or activate an altar. No global solvability or
automatic blocked-run defeat detector was added.

## Provisional rules and configuration

These are prototype defaults for team review, not newly confirmed final rules.
Existing D01–D13 decisions are preserved.

| Setting | Default |
|---|---|
| Board | 7×7. |
| Start | A4, doors north/east/south. |
| Altars | G1, doors south/west; G7, doors north/west. |
| Sealed core | G4, doors north/south/west; initially locked. |
| HP | Initial 6, maximum 6, minimum 0. |
| Supplies | Initial 2, maximum 5, minimum 0. |
| Supply / danger / neutral | +1 Supplies / -1 HP / no resource change. |
| First altar milestone | +1 Supplies, once for whichever altar is entered first, capped normally. |
| Door Seal | Cost 1 Supplies, at most 3 successful uses per run. |
| Emergency Chisel | Cost 2 Supplies, at most 2 successful uses per run. |
| Victory | Actual entry into the core after all configured altars activate. |
| Defeat | HP reaches zero. No hard turn limit or speculative blocked-state defeat. |

Room-type and category weights are unchanged. `objectives.start` and `core`
contain `{pos, doors}`; `objectives.altars` is a configurable nonempty list of
`{id, pos, doors}`. Two altars are the default, while other counts are tested.
`first_altar_supplies` and the existing item costs/limits are configurable.

The new Chisel proposal connects two existing rooms, replacing the older
provisional suggestion of opening a wall toward an empty cell. It preserves
strict matching and cannot operate on locked endpoints or bypass core activation.
Door Seal must retain a reachable entrance and match every occupied neighbor.
Invalid uses charge nothing. Supplies do not regenerate automatically.

Level validation checks bounds, overlaps, unique ids, fixed-room edge agreement
and optimistic routes through flexible empty cells. Altars must have potential
routes without crossing the locked core. This does not prove every card sequence
or seed can win; draw protection guarantees a current legal option only.

## Automated verification

- Integrated Phase 4 baseline: **404 passed**, warnings enabled and isolated
  sandbox temporary/cache paths.
- Final reviewed desktop-account command
  `.venv\Scripts\python.exe -m pytest -q`: **563 passed in 7.58s**, no warnings
  or errors. All original 404 tests remain present and pass.
- `.venv\Scripts\python.exe -m pytest -ra -W default`: **563 passed in 7.59s**,
  no warnings or errors.
- New coverage: 57 level tests, 50 pure-tool tests, 29 MVP integration tests,
  19 MVP UI test cases, and 4 recorded-playthrough tests: **159 new test cases**.
- `git diff --check`: clean; original and new files reviewed.
- `python -m engine.demo`: verified WON through public actions, without
  manipulating cards, rooms, resources or random state.
- The same default-config sequence completes through Pygame selection,
  rotation and map-click events, with rendering checked for state mutation.
- A configured 1-HP danger-room entry verifies LOST. A blocked fixture verifies
  Chisel recovery, protected dealing, resource payment and later first entry.
- Forced exceptions after event/draw/tool/objective preparation verify rollback
  of the board, player, hand, RNG, resources, activation and tool usage.
- Real winning and losing headless screenshots were inspected. Physical desktop
  input, display scaling and subjective usability remain manual checks.

No new dependencies or warning filters were added. Sandbox verification follows
AGENTS.md to avoid recreating desktop-account temporary/cache ACL conflicts.

## Verified winning playthrough

Launch a fresh game:

```powershell
.\.venv\Scripts\python.exe main.py --seed 159
```

Cards are numbered 1–3. The R column is the number of clockwise quarter-turns
from a freshly dealt card. Do not use tools or add other builds during this
recorded example. Construction can use any reachable frontier, while walking
itself remains one adjacent room at a time.

| Step | Action | Card | R |
|---:|---|---:|---:|
| 1 | Build B4 | 2 | 1 |
| 2 | Build C4 | 3 | 1 |
| 3 | Build D4 | 2 | 1 |
| 4 | Build E4 | 1 | 1 |
| 5 | Build F4 | 2 | 0 |
| 6 | Build F3 | 1 | 0 |
| 7 | Build F2 | 2 | 0 |
| 8 | Build F1 | 1 | 1 |
| 9 | Walk to G1; activate altar A | — | — |
| 10 | Build F5 | 1 | 0 |
| 11 | Build F6 | 3 | 0 |
| 12 | Build F7 | 2 | 0 |
| 13 | Walk to G7; activate altar B and unlock the core | — | — |
| 14–18 | Walk F7 → F6 → F5 → F4 → G4 | — | — |

Expected result: **WON**, 11 builds, both altars active, HP **5/6**, Supplies
**5/5**, no tools used. Events are eight neutral, one danger and two supply.

To replay and print these actions without opening a window:

```powershell
.\.venv\Scripts\python.exe -m engine.demo
```

This verifies one successful default seed and sequence, not universal solvability.

## Manual testing checklist

The detailed checklist is in [TEST_PLAN.md](TEST_PLAN.md). Before marking manual
acceptance complete:

1. Launch seed 159 and reproduce the recorded victory on a real display.
2. Verify objective locations/labels, category previews and all resource values.
3. Attempt premature core entry, revisits, invalid steps and special-room
   overwrites; confirm no free rewards or unauthorized activation.
4. Use F/Seal to cycle doors and cancel; confirm modified geometry, charges and
   usage limits only on successful placement. Card changes/rotation cancel modes.
5. Use C/Chisel on an adjacent existing wall pair; verify both doors, payment,
   unchanged player position and activation only after subsequent real entry.
6. Try insufficient resources, exhausted tools, empty/non-adjacent targets and a
   locked core; confirm no state changes or charges.
7. Verify blocked construction still allows walking/tools/restart. Do not assume
   every blocked state is recoverable.
8. Check defeat on HP zero, terminal input blocking, all restart buttons/N, Esc,
   window close and subsequent launch.
9. Check Windows scaling and text clipping; try other seeds and record build
   count, choices, tools, resources, outcome and subjective difficulty.

## Balance observations and remaining issues

No balance values were changed without evidence. The recorded win uses eight
straight rooms, two corners and one cross, demonstrating that simple rooms
remain useful and a cross is useful for branching. That run ends at the Supplies
cap, so it alone cannot establish that the economy is well balanced or that
tools are sufficiently attractive. Dedicated recovery tests show Chisel can
unlock progress at a real, limited cost, and Door Seal can repair an otherwise
illegal room while retaining strict matching.

Final review corrected a misleading sealed-card fit label and stale activation
feedback on altar revisits; the regression cases failed before the fixes and
pass afterward. No known P0/P1 defect remains from automated and headless checks. Outstanding
work is physical desktop acceptance, broader strategy/seed playtesting and team
confirmation of provisional objective, tool and balance rules. Some seeds and
choices may become blocked; this is not misreported as a loss or a solvability
guarantee. No Boss, combat, extra floors or Final Goal work was added.

## Language distribution and Git diff summary

Authored source is **100% Python**: **30 `.py` files**, **4,179 source lines**.
The same method as Phase 4 includes tracked and new non-ignored source and
excludes blanks, comment-only lines, Python docstrings, dependencies, caches,
data and documentation. This is strictly above the required 50%.

Before publication, the change set consisted of **10 modified tracked files**
and **12 new files**, including both delivery and final-review reports. The
tracked `git diff --stat` was **325 insertions and 71 deletions**, excluding the
then-untracked new files. No existing tests or Phase 4 engine modules were
removed. These figures describe the reviewed working-tree snapshot.

## Readiness assessment

The complete engine and input-driven UI loop have a verified default-config win,
defeat, blocked recovery and restart, with all 563 tests passing. The appropriate
status is **MVP FUNCTIONAL — MANUAL VERIFICATION REQUIRED**. The desktop
checklist remains outstanding even when publication is authorized; this report
does not mark physical playtesting or final balance decisions complete.
