# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.1] — 2026-07-12

### Added
- Arithmetic comparisons in rules (`>`, `>=`, `<`, `<=`, `=:=`, `=\=`)
- Negation operator (`NOT` → Prolog `\+`)
- Multi-line rule parsing (body on next lines)
- Conjunction queries with variable deduplication
- IT Security & Compliance demo (3,872 facts, 10 questions)
- Unit tests for new features (25 total, all passing)
- MCP Registry metadata (`server.json`)
- GitHub Actions workflow for PyPI publishing

### Changed
- Updated MCP server `instructions` with new capabilities
- Translated `pyproject.toml` description to English

### Fixed
- Meta-interpreter now handles built-in arithmetic operators
- Query conjunctions correctly wrapped in Prolog parentheses
- NOT operator converted to Prolog negation (`\+`)
- Multi-line rules no longer split into separate statements

## [0.1.0] — 2026-07-01

### Added
- Initial release
- Euclid IR parser (text + YAML formats)
- Prolog translator with meta-interpreter for proof trees
- MCP server with `reason` tool
- Examples: genealogy, RBAC, classification, loan eligibility, compliance auditor
