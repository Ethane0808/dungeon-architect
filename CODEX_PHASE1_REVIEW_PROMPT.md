# Dungeon Architect — Codex Phase 1 Review Prompt

You are reviewing a Python 3.14.7 + pygame-ce game project after Antigravity completed Phase 1. First perform a **read-only review**; do not change files until I approve the fixes.

Read `README.md`, `GAME_DESIGN.md`, `DECISIONS.md`, `TECH_SPEC.md`, `TEST_PLAN.md`, and the implemented source code and tests. Determine what Phase 1 actually includes; do not label unfinished MVP/Final Goal features as bugs.

Review the implemented systems for correctness: 7×7 grid coordinates and bounds; N/E/S/W rotation; strict door-to-door and wall-to-wall matching with **every occupied neighbor**; legal reachable frontiers; three-card selection and legal-card guarantee; state consistency; pygame logic/UI separation; and headless automated testability. Run existing tests if feasible and clearly distinguish actual test results from unverified assumptions.

**Programming language requirement**: other languages are permitted when technically justified, but Python must remain the primary language and make up **strictly more than 50% of all team-authored source code**. For this project, unless the course specifies otherwise, report nonblank, non-comment source lines (SLOC) for each language, counting application code, tests and scripts; exclude vendored dependencies, generated files, caches, compiled output, assets, documents, data files and lockfiles. Report the exact numerator, denominator and percentage, your file inclusion/exclusion assumptions, and whether the rule is met. Do not add artificial or duplicated Python lines to increase the ratio. Flag a violation as P1.

Output a structured review with (1) implemented features, (2) P0/P1/P2 findings with file:line, impact and evidence, (3) missing tests, (4) architecture suggestions ranked by necessity, (5) the source-language breakdown and compliance verdict, and (6) a minimal ordered fix plan. Do not add Boss mechanics or change confirmed gameplay rules.

**Wait for approval before making any changes.** After approval, make only the agreed fixes on a separate branch, add regression tests, rerun tests, recalculate the language ratio, and summarize modified files and residual risks.
