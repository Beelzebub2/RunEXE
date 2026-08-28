# Changelog

All notable RunEXE changes are documented here.

## [0.3.0] - 2026-08-28

### Added

- Proton runtime discovery across Steam libraries, Valve builds, Proton Experimental, GE-Proton, Flatpak, Snap, and custom installations.
- Backend selection with `--backend auto|wine|proton`, direct `--proton` selection, the `backends` command, and `RUNEXE_PROTON_PATH` support.
- Standalone Proton launching with isolated compatibility data and the Steam compatibility environment variables Proton expects.
- AppX/MSIX and AppX/MSIX bundle input support, including manifest parsing, architecture-aware package selection, declared executable discovery, and reusable package caching.
- Safe package extraction with archive size/file-count limits, symbolic-link rejection, and path-traversal protection.
- Rich terminal presentation with launch plans, summary tables, status colors, runtime hints, and an ASCII-safe brand mark for legacy CMD code pages, CI, and SSH sessions.
- `python -m runexe` invocation support.
- Project logo assets and README branding.
- Regression coverage for Proton discovery, runtime selection, package handling, backend conflicts, and launch environment construction.

### Changed

- Bumped the package version to 0.3.0 and updated the package description, classifiers, metadata, and roadmap.
- Game compatibility now prefers Proton when a suitable installation is available, while ordinary applications continue to prefer Wine.
- Users can explicitly override runtime selection when automatic classification is not appropriate.
- Proton dependency installation is opt-in; Wine dependency provisioning remains automatic by default.
- CLI help, error handling, JSON output, argument forwarding, timeout handling, and launch diagnostics were refined for more predictable automation.
- README usage, requirements, runtime behavior, package limitations, and development verification instructions were expanded.

### Compatibility notes

- AppX/MSIX packages are launched through their declared executable. Package identity, Microsoft Store services, and UWP-only behavior are not recreated.
- Proton is invoked directly through its `proton run` interface. Some games may still require Steam services or title-specific configuration.
- Wine/Proton integration was not exercised in the Windows development environment; runtime behavior should be verified on a Linux host with the target compatibility tools installed.

### Verification

- 30 automated tests passed.
- Ruff lint and format checks passed.
- Source distribution and wheel build passed.
- ASCII-codepage CLI smoke test passed.

## [0.2.0] - 2026-08-28

### Added

- Defensive, bounded PE parsing for headers, sections, imports, manifests, and version resources.
- Safer .NET detection, including apphost `runtimeconfig.json` files and Desktop versus Runtime classification.
- Broader runtime dependency detection for Visual C++, DirectX, XInput, OpenAL, XAudio, Windows codecs, RichEdit, and related libraries.
- Deterministic Wine prefixes with architecture validation, Windows version overrides, custom prefix paths, dependency controls, timeouts, and working-directory-aware launches.
- JSON compatibility reports and host-check controls.
- Initial AppX/MSIX materialization support and packaged Win32 launch warnings.
- Development tooling, initial regression suite, and project-level ignore rules.

### Changed

- Compatibility reporting now separates blocking issues, warnings, notes, selected backend, and required Winetricks verbs.
- Game classification became conservative to avoid treating ordinary graphics applications as games.
- Anti-cheat findings became compatibility warnings rather than automatic blockers where Proton support may be title-specific.
