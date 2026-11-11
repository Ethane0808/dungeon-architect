# Phase 4 delivery

Implemented on `feature/events-resources`, based on clean commit `ed2ddaf`, with
the completed Phase 3 construction sandbox in its history. Prepared for review
against `main`; desktop gameplay testing remains pending.

## Implementation

Ordinary room events now resolve once on first entry. The existing card preview
category is preserved on the placed room. Building already automatically entered
the new room in Phase 3, so that entry resolves the event; there is no separate
placement reward. Subsequent visits do not resolve it again, even if its original
reward was capped to zero.

The inspected Phase 3 code supported automatic entry but had no walking controls.
This implementation adds one-room steps through matching, unlocked doors using
arrows, WASD or clicks on adjacent existing rooms. Walking preserves the hand,
selection, card rotations, build turn and RNG. Returning to visited rooms costs
no resources. Existing construction across the reachable region is preserved.

The existing UI now displays HP, Supplies, and a persistent LAST EVENT panel with
the event message and actual bounded resource changes. Preview and hover never
resolve events. Restart restores the original seed, initial resources, board and
hand, and clears the notification.

## Architecture and APIs

`engine/events.py` contains immutable `EventOutcome`, `EventConfig` and
`EventNotification` data and the pure `resolve_event` function. The existing
card RNG chooses geometry-dependent categories; each category currently has one
configured outcome. Resolving it does not consume RNG or alter the established
card sequence. Exact effects are shown only after entry.

`BuildSession.move` and the existing automatic-entry `place` path share
`_prepare_entry`. They prepare resource changes and an updated Tile before
committing. Placement also prepares the next hand first. A resolution or draw
failure leaves the board, player, resources, notification and hand intact; a
failed draw also restores RNG. A resolved room stores its actual resource deltas
in `Tile.event_outcome` and sets `event_resolved=True`.

| API | Contract |
|---|---|
| `Resources(hp, hp_max, supplies, supplies_max=None, supplies_min=0)` | Immutable validated snapshot. HP is within 0..hp_max; Supplies within the configured bounds. Invalid initial states and non-integer values, including bool, are rejected. |
| `resources.apply(hp_delta=0, supplies_delta=0)` | Return a new snapshot, clamping integer changes to bounds. Supports damage, healing, rewards and negative supply changes. |
| `load_resources(path=DEFAULT_CONFIG_PATH)` | Load initial HP, maximum HP, initial Supplies and optional Supplies bounds from the player configuration. |
| `resources.hp_depleted` / `session.hp_depleted` | True at zero HP; this phase does not invent a defeat screen or stop further actions. |
| `EventConfig.from_mapping(data)` / `load_event_config(path)` | Validate categories and configurable messages/effects. Reject missing categories, unknown effect keys and invalid deltas. |
| `resolve_event(category, pos, resources, config)` | Return new Resources and an EventNotification containing actual bounded changes; no game-state mutation. |
| `BuildSession(..., resources=None, event_config=None)` | Optionally inject initial resource and event settings. Restart reuses that initial resource snapshot. |
| `session.movement_preview(pos)` / `session.move(pos)` | Validate or execute one adjacent step; return `(ok, reason)`. Invalid movement never triggers an event. |
| `session.current_event` | Last new event, or None after restart; unchanged by revisits and invalid actions. |

Detailed integration documentation is in [TECH_SPEC.md](TECH_SPEC.md).

## New and modified files

| Files | Change |
|---|---|
| `engine/events.py`, `engine/resources.py` | New event and bounded-resource modules. |
| `engine/game.py` | Atomic entry integration, walking, resource/notification state and restart. |
| `engine/models.py`, `engine/cards.py` | Update data and module documentation to reflect resolved events. |
| `data/prototype_config.json` | Add event messages; preserve existing numeric values and weights. |
| `ui/app.py`, `ui/screens.py` | Walking inputs, movement feedback, resource HUD and event panel. |
| `main.py` | Update launch module description. |
| `tests/test_events.py`, `tests/test_resources.py` | New event, resource, movement, configuration and failure tests. |
| `tests/test_game.py`, `tests/test_ui.py` | Include resources/events in transaction checks; test new controls and HUD. |
| `README.md`, `GAME_DESIGN.md`, `DECISIONS.md`, `TASKS.md` | Update current behavior, progress and provisional design record. |
| `TECH_SPEC.md`, `TEST_PLAN.md`, `PHASE4_REPORT.md` | API documentation, manual checklist and delivery report. |
| `AGENTS.md`, `DEVELOPMENT_GUIDE.md` | Isolate sandbox test directories and explain Windows test-folder permission diagnosis. |

## Verification

The installed Python initially lacked pytest and pygame-ce. The existing
`requirements-dev.txt` dependencies were installed into ignored local `.venv`;
no new project dependency was added. Python 3.14.7 was used.

- Baseline: **315 passed**.
- Implementation: **404 passed**, using `.venv/Scripts/python.exe -m pytest -q`.
- The full suite includes previous rotation, strict placement, BFS, protected
  three-card draws, restart, entry-point and SDL dummy UI checks.
- New coverage includes first entry and repeated visits; invalid movement and
  previews; category consistency and fixed seeds; HP damage/healing/zero;
  Supplies bounds; recovery from failed events/draws; locked rooms; restart;
  walking while construction is blocked; HUD text, marker position and fit.
- `git diff --check` passes. Changes were reviewed, and an SDL dummy screenshot
  was inspected for HUD/event-panel readability.

The tests do not open an interactive window. Physical Windows scaling and
actual playtesting still require manual verification.

### Follow-up: Windows test-directory permissions

The desktop command `.venv\Scripts\python.exe -m pytest -ra -W default` initially
reproduced **402 passed, 2 errors and 2 warnings** under `MSI\suche`, even though
the same suite passed under `MSI\CodexSandboxOffline`.

Both errors occurred before the test bodies in
`test_default_path_is_independent_of_working_directory` and
`test_custom_config_path_and_input_snapshot`. Pytest's `tmp_path` fixture called
`TempPathFactory.getbasetemp`, which reached `find_prefixed` / `os.scandir` and
received WinError 5 on `%TEMP%\pytest-of-suche`.

Both warnings came from `cacheprovider.Cache.set`: writes to
`.pytest_cache\v\cache\nodeids` and `lastfailed` failed while ensuring their
parent directory, reporting WinError 183. The path was an existing directory,
not an incorrectly named file; its Windows ACL prevented desktop access.

Inspection showed both roots and their generated contents were owned by the
sandbox account, with access only for the owner, SYSTEM and Administrators.
This was an environment/fixture setup issue, not a Phase 4 gameplay, import,
Pygame initialization or cleanup failure. The two affected tests predate Phase 4.

The smallest fix was to restore normal inherited ACLs on only those two generated
pytest directory trees, using the owning account. No files were deleted, no
gameplay or test code was changed, and no warnings were suppressed. Future
sandbox runs must use fresh explicit `--basetemp` and separate `cache_dir` paths;
see [AGENTS.md](AGENTS.md). The existing failing tests and complete suite provide
the regression checks for the repair.

Post-repair verification under the desktop account, with the original default
temporary/cache paths and warning reporting still enabled:

- `.venv\Scripts\python.exe -m pytest -q`: **404 passed**, no errors or warnings.
- `.venv\Scripts\python.exe -m pytest -ra -W default`: **404 passed**, no errors
  or warnings.
- `git diff --check`: clean.

### 2026-11-12 revalidation and commit readiness

The inherited permissions still grant the desktop account access to both pytest
directory trees. A fresh diagnostic run under `MSI\suche` with
`.venv\Scripts\python.exe -m pytest -ra -W default` passed all 404 tests; the
original errors and warnings did not recur.

The two requested final commands were then run sequentially under the same
desktop account, using the default temporary/cache paths:

| Command | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q` | 404 passed; no errors or warnings. |
| `.venv\Scripts\python.exe -m pytest -ra -W default` | 404 passed; no errors or warnings. |
| `git diff --check` | Clean. |

Only this report was updated during this recheck. The prior investigation
updated `AGENTS.md` and `DEVELOPMENT_GUIDE.md` to prevent the account collision;
the actual repair changed only permissions on generated pytest folders. No
gameplay or test implementation changes were necessary for the permission
failure. No new regression tests were added: the two existing `tmp_path` tests
directly check the repaired setup, and the full suite checks gameplay regressions.
Warnings were neither filtered nor disabled.

Phase 4 is ready to commit and open for review based on automated verification.
Physical desktop gameplay/scaling checks remain pending. The investigation
preserved the existing `feature/events-resources` branch and all development
changes. Publication is a separate, user-authorized step after verification.

## Manual gameplay checklist

Launch `.venv/Scripts/python.exe main.py --seed 42` and then repeat with a
different seed. The full checklist is in [TEST_PLAN.md](TEST_PLAN.md).

1. Verify initial HP 6/6 and Supplies 2/5; preview and rotate without changes.
2. Build each event category and check automatic entry, one resource update,
   matching category/message, and the refreshed protected hand.
3. Walk back and forth with arrows, WASD and adjacent-room clicks; check that
   cards, rotations, resources and build turns are preserved.
4. Try invalid steps and placements; check that no event or reward occurs.
5. Check capped Supplies and zero HP, including clear messages and safe restart.
6. Restart using both N and the button; check initial values and seeded replay.
7. Check readability, colors and clipping on an actual display; confirm walking
   remains available when no normal placement is possible.

## Source-language distribution

Authored source is **100% Python**: **21 `.py` files**, **2,661 source lines**.
The count includes tracked and new, non-ignored source files, excludes blank
lines, comment-only lines and Python docstrings, and excludes dependencies,
virtual environments, caches, data and documentation. No other authored source
language was found. This exceeds the strictly-more-than-50% requirement.

## Fixes, limitations and provisional design

The missing walking controls are now implemented. First-entry resolution guards
prevent duplicate rewards and damage; preparation before commit prevents partial
resource changes after a failed next-hand draw. Existing gameplay tests pass.
No additional verified defects remain from this change; desktop playtesting is
still outstanding.

All existing P08 balancing values remain **provisional**, including:

- HP starts at 6 with maximum 6; Supplies starts at 2 with maximum 5 and lower
  bound 0. Supplies can optionally use another nonnegative lower bound or no cap.
- Supply gives +1 Supplies; danger gives -1 HP; neutral changes neither resource.
- Category weights remain 2/2/6 for dead ends, straights and corners, 3/2/5 for
  T junctions and 3/3/4 for crosses, in supply/danger/neutral order.

The engine supports configured healing, negative supply effects and additional
categories such as mystery, but no new default category, probability or effect
was invented. No automatic regeneration, exploration fee, milestone reward,
item cost/ability, boss or final objective/defeat system was added. In particular,
zero HP is an explicit state for future rules, and no normal construction being
possible still does not automatically mean defeat.

## Phase 5 readiness

The engine and automated regression checks are ready for the next feature phase.
Complete the desktop checklist and review these changes first.
Before implementing tools or the final game loop, confirm item effects, prices,
usage limits, milestone rewards, altar/core layout and final defeat conditions.
This phase's provisional numbers should be evaluated through playtesting rather
than promoted to finalized rules.
