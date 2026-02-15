# Changelog

All notable changes to Shadow Bureau backend will be documented in this file.

## [1.0.0] - 2026-02-14

### Added
- Initial release for Hack_NCState 2026
- Blackboard architecture with 7 knowledge sources
- Dual graph system (in-memory + Neo4j AuraDB)
- 4 Backboard AI agents (Claim Analyst, Fact Checker, Alert Composer, Case Synthesizer)
- Real-time WebSocket updates
- Public alert system
- Comprehensive API documentation

### Removed
- Auth system (not needed for hackathon demo)
  - Removed `app/routers/auth.py`
  - Removed `app/routers/deps.py`
  - Removed `app/models/auth.py`
  - Removed dependencies: `passlib[bcrypt]`, `python-jose[cryptography]`
  - Removed config: `jwt_secret`, `officer_email`, `officer_password`
- Dead code in `orchestrator.py`
  - Removed unused `_wrap_clustering()` function
  - Removed redundant `handle_report_received()` event handler
- Unused imports across codebase

### Changed
- All routes are now public (no authentication required)
- Simplified configuration (3 fewer environment variables)
- Cleaner codebase (~120 lines of code removed)

### Fixed
- No breaking changes
- All tests passing (14/14)
- All pipelines operational

---

## Development Notes

- **Project Type:** Hackathon prototype
- **Focus:** Feature demonstration over security
- **Auth:** Intentionally disabled for public access
- **Storage:** In-memory primary, Neo4j optional
- **Testing:** Manual only (no automated test suite yet)
