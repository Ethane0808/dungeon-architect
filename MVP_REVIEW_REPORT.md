# MVP final review — 2026-11-13

**MVP FUNCTIONAL — MANUAL VERIFICATION REQUIRED**

## A. Review summary

The reported delivery results were independently reproduced before fixes:
both requested pytest commands passed 560 tests without warnings, and the
documented seed 159 demonstration reached WON after 11 builds with HP 5/6 and
Supplies 5/5. This review found and fixed two P2 feedback defects. No verified
P0/P1 defect remains from automated, code and headless UI checks.

Review covered the design/decision documents; engine controllers, cards,
placement, movement, events, resources, level validation, tools and demo; UI and
entry points; configuration; and the existing regression suite. Confirmed strict
matching, draw protection and free backtracking were distinguished from the
provisional objective layout, tool prices/limits, milestone and defeat rules.
No configuration values or gameplay rules were changed during stabilization.

The transaction model is appropriate for a 7×7 game: immutable configurations
and resources, replaced Tiles, copied candidate containers and cloned RNG state
prevent failed operations from mutating the live state. Structural changes
refresh legal metadata, preserving existing cards and rotations. No complex
caching, global solvability detector or architecture replacement was added.

## B. Findings and severity

### P2-01: sealed room displayed stale normal-card playability

- Location: `ui/screens.py:291`, selected-card playability text.
- Reproduction: use default seed 3, select card 1 (a dead end), then press F to
  seal its only door. There are no legal placements and no entrance remains.
  The room artwork showed that seal but still said “Fits in some rotation.”
- Cause: the renderer read `draw_result.legal_card_indices`, which describes the
  original normal card, while drawing the modified card.
- Fix: for the selected card with a pending seal, use the already computed
  sealed-placement set and explicitly label current-rotation fit or no fit.
  Other cards retain normal playability text. This does not change engine rules.
- Regression: `tests/test_mvp_ui.py:227`,
  `test_sealed_card_label_matches_the_displayed_room_legality`. The invalid
  dead-end case failed before the fix; a valid default-seed cross case also
  protects the positive label. Rendering must preserve the game snapshot.

### P2-02: revisiting an altar replayed another altar's activation message

- Location: `ui/app.py:55`, `GameApp.move`.
- Reproduction: in the supported adjacent-objective test level, walk from A4
  through altar A at B4 to altar B at C4, then return to B4. The UI repeated
  “Altar B activated. Core unlocked!” even though this was a free revisit.
- Cause: every successful move onto any altar copied the controller's last
  `objective_message`, even when no objective changed.
- Fix: show objective feedback only if activation changed or the move won at
  the core. Revisits retain ordinary movement feedback; LAST EVENT correctly
  retains its history, and rewards/objectives are untouched.
- Regression: `tests/test_mvp_ui.py:245`,
  `test_revisiting_an_altar_shows_movement_instead_of_stale_activation`. It
  failed before the fix and checks message, resources, event and activation.

No P0/P1 findings were verified. No speculative engine or balance changes were
made to manufacture additional findings. There were no dependency warnings to
suppress or document as unresolved.

## C. Fix scope

Only these paths were changed by this final-review work:

| Path | Review change |
|---|---|
| `ui/screens.py` | Use current sealed-card legality for its fit label. |
| `ui/app.py` | Distinguish new activation from an ordinary altar revisit. |
| `tests/test_mvp_ui.py` | Two regression functions, three cases including valid/invalid sealed cards. |
| `TEST_PLAN.md` | Add physical checks for both corrected feedback paths. |
| `MVP_REPORT.md` | Update final test/source counts and link this review. |
| `MVP_REVIEW_REPORT.md` | Record independent evidence and readiness. |

All pre-existing Phase 5 changes, including untracked files, were preserved.
Engine/configuration files were inspected but not changed by this review.

## D. Test results

Python 3.14.7, pygame-ce 2.5.8 and pytest 9.2.0 were used. No dependencies were
added or updated. Desktop-account runs used `MSI\suche` and the normal pytest
temporary/cache paths. Sandbox checks used isolated paths per AGENTS.md.

| Stage / command | Actual result |
|---|---|
| Baseline `.venv\Scripts\python.exe -m pytest -q` | 560 passed in 8.70s. |
| Baseline `.venv\Scripts\python.exe -m pytest -ra -W default` | 560 passed in 7.76s; no warnings. |
| Baseline `.venv\Scripts\python.exe -m engine.demo` | WON, 11 builds, HP 5/6, Supplies 5/5, altars 2/2. |
| New negative UI regressions before fixes | Both failed for the reported messages. |
| UI/demo suite after fixes | 90 passed with warnings enabled, before adding the positive parameter case. |
| Final targeted UI regressions | 3 passed. |
| Final `.venv\Scripts\python.exe -m pytest -q` | **563 passed in 7.58s**, no errors or warnings. |
| Final `.venv\Scripts\python.exe -m pytest -ra -W default` | **563 passed in 7.59s**, no errors or warnings. |
| Final `.venv\Scripts\python.exe -m engine.demo` | **WON**, original 11-build sequence/resources unchanged. |
| `git diff --check` | Clean. |

Application startup/shutdown was also exercised with SDL dummy: `main.main`
started, rendered a frame, exited via QUIT and Esc in separate runs, and cleaned
up Pygame, display and font state. The input-driven seed 159 replay passed with
20 duplicate clicks after every recorded action and 20 subsequent restarts.
This verifies headless application behavior, not real desktop interaction.

## E. Gameplay verification

### Winning, losing and recovery scenarios

- The pure-engine replay and Pygame input-driven replay both complete default
  seed 159. Both altars require actual entry; unlock alone does not win; entering
  the core reaches WON once. Terminal gameplay is blocked and restart works.
- The existing deterministic 1-HP danger-room scenario reaches LOST, preserves
  the event's one-time resolution and rejects subsequent gameplay. Default
  multi-seed runs also reach legitimate HP-zero losses, described below.
- The existing blocked fixture pays two Supplies to Chisel an existing wall
  pair, restores reachability and a protected hand, and remains PLAYING. The
  tool does not auto-enter or trigger an ordinary event/altar; real entry does.
- Thirty additional public-API scenarios exercised 1–5 custom-id altars,
  Supplies lower bounds 0/1 and milestone rewards 0/1/100. All passed actual
  entry, bounded first-only rewards, core gating, terminal rejection, stable
  exploration RNG and restart checks.

### Multi-seed policy checks

Checked default-config seeds **0–49 and 159**, each repeated deterministically,
plus the documented seed 159 replay. The bounded policy walks shortest built
paths to reachable objectives, otherwise chooses actual dealt cards ranked by
objective distance, useful exits and event risk; it periodically exercises
affordable seals and tries Chisel on construction blockage. Limits were 49
builds/200 progress actions; no run hit either limit. Actual maxima were 40
builds and 69 progress actions.

| Policy outcome across 51 unique seeds | Count |
|---|---:|
| WON | 31 |
| Construction blocked, correctly still PLAYING | 18 |
| LOST at HP zero | 2 |
| Crashes / invariant failures / action-limit stops | 0 / 0 / 0 |

The HP-zero losses were seeds **16 and 41**, each after exactly six danger
events. Terminal freezing and restart passed. These are expected defeats.

The blocked policy runs were **5, 7, 10, 12, 17, 18, 19, 20, 22, 24, 25, 31,
34, 38, 40, 43, 46 and 159**. At those states, the harness found no legal dealt
normal/sealed placement, no affordable valid Chisel, and no reachable remaining
objective. The engine correctly left them PLAYING with restart available.
These are strategy outcomes, not proof those seeds are inherently unsolvable.
Seed 159 is an explicit counterexample: the greedy run blocked, but the recorded
sequence wins. No implementation defect was found from an unsuccessful run.

Independent geometry/reachability and resource-ledger checks recorded:

- 4,557 complete state checks and 4,435 independent protected-draw checks.
- 17,816 invalid-action atomicity checks and 3,938 locked-core checks.
- 1,456 free-backtracking steps, 268 terminal-freeze checks and 103 restarts.
- 51 exact deterministic repeats.
- 152 successful Door Seals and 33 Chisels across the unique policy runs, all
  within configured costs and limits.

The one-off harness and compact results remain in ignored local paths
`.venv/mvp_review_seeds.py` and `.venv/mvp-review-seeds.json`. They can be rerun
from the project root with `.venv\Scripts\python.exe .venv\mvp_review_seeds.py`;
they are diagnostic artifacts, not new production dependencies or features.
The persistent test suite and documented winning replay remain the team-facing
regression checks. Policy outcomes are not a balance or universal-win guarantee.

## F. Remaining issues and manual acceptance

No known P0/P1 defect remains from this review. Both verified P2 findings are
fixed. Physical Windows input/display behavior and final team acceptance remain
pending. All objective layouts, prices, usage limits, event values and weights
retain their existing provisional status.

Before approving the merge, use a real Windows display to:

1. Launch `main.py --seed 159`, follow the table in MVP_REPORT.md, and verify the
   complete win/restart sequence with mouse and keyboard.
2. Check grid/cursor alignment and text at the team's actual display scaling;
   inspect tools, objective checklist, HUD, event panel and both overlays.
3. Check valid/invalid seal labels, altar revisit messages and LAST EVENT history.
4. Exercise tool charges, limits, invalid targets, locked-core rejection and
   free backtracking. Chisel must not auto-enter or activate a target.
5. Verify no action changes terminal state until Restart/N; test title-bar
   close, Esc and reopening. Repeat rapid clicks/keypresses.
6. Try other strategies/seeds and record blockage, resource scarcity and tool
   usefulness without interpreting every blocked run as a bug.

The detailed acceptance list is in TEST_PLAN.md. No physical desktop interaction
was performed by this review, so this report does not declare it verified.

## G. Language and Git status

Authored source is **100% Python**: **30 `.py` files**, **4,179 source lines**.
As before, counting excludes blank lines, comment-only lines, Python docstrings,
dependencies, caches, generated diagnostic artifacts, data and documents. No
other authored source language is present; the share exceeds 50% without adding
production features or padding code.

At review completion, the branch was **feature/mvp-completion**, based on
**ac70604**. During review nothing was reset, rebased, discarded, committed,
pushed, published as a PR or merged, and `main` was not modified. The user
separately authorized publication and merge after this review.

The reviewed Phase 5 working set plus fixes contained **10 modified tracked
files and 12 untracked new files**. The tracked `git diff --stat` was
**325 insertions and 71 deletions**; new files are not included until staged.
The six review-specific paths are listed in section C; the other changes belong
to the preserved Phase 5 implementation. The index was unstaged at that point.

## H. Readiness decision

**MVP FUNCTIONAL — MANUAL VERIFICATION REQUIRED**

The engine and input-driven loop have reproducible wins, expected losses,
recovery and restart; all 563 tests pass with warning reporting enabled; broader
deterministic checks found no engine defect; and the two confirmed minor UI
bugs are fixed with regressions. Automated review supports final team review.
Physical desktop acceptance remains outstanding; publishing or merging does not
mark it verified. No new Boss, Final Goal, balance or unrelated features were introduced.
