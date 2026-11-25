# Preferences

- 2026-11-26: Keeping the codebase small (minimal or negative net LOC) is highly prized; prefer public library APIs (such as public `yfinance` properties) over private internals.
- 2026-11-26: Align P/E Monitor figures with values users can directly verify on Yahoo Finance's web pages.
- 2026-11-26: For UI provenance popups, show intuitive numeric formulas (such as `price / eps = pe` with a mismatch check) instead of raw code strings; omit popups on raw non-computed columns.
