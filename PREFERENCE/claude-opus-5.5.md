# PREFERENCE (claude-opus-5.5)

- 2026-11-28: CI fixes must not change code behavior; change only what the checks need.
- 2026-11-28: Do not use `Any` to silence mypy. Follow the logic and give the narrowest correct type; keep any unavoidable `Any` to the smallest scope.
- 2026-11-28: Keep net LoC growth minimal; prefer inline fixes over added lines.
- 2026-11-28: Do multi-part fixes in steps, with one commit per step.
