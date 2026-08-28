# RunEXE

Analyze Windows software and launch it on Linux through the best available Wine or Proton runtime.

<p align="center">
  <img src="assets/runexe-logo-v2.png" alt="RunEXE terminal-to-launch logo" width="360">
</p>

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-LGPL--2.1-green) ![Status](https://img.shields.io/badge/status-alpha-orange)

See the detailed [changelog](CHANGELOG.md) for the 0.3.0 release notes.

RunEXE inspects PE executables and AppX/MSIX packages before launch, reports likely compatibility concerns, discovers installed Wine and Proton runtimes, and creates an isolated per-application environment. Games prefer Proton when it is available; ordinary applications prefer Wine, with explicit overrides for either backend.

## ✅ Tested Applications

The following have been run through RunEXE with **no additional setup** beyond what the tool provisions automatically:

- Notepad++ (Native)
- Notepad++ (32-bit)
- PuTTY.exe (Native)
- KeePass (.NET)

More compatibility data is one of the long-term goals of the project (see [Roadmap](#-roadmap)).

## 🚀 Features

- **Defensive PE analysis** - bounded, read-only parsing of file-backed PE data (Wine is not required)
- **AppX/MSIX support** - extracts trusted package archives, reads `AppxManifest.xml`, and finds the declared application executable
- **Architecture detection** - x86 / x86_64 / ARM64, mapped to the correct `WINEARCH`
- **Import table analysis** - full DLL + function listing (`--imports`)
- **Subsystem parsing** - Windows GUI vs. Console vs. others
- **Embedded manifest extraction** - reads `RT_MANIFEST`, surfaces the requested execution level (e.g. `requireAdministrator`)
- **Version info parsing** - `VS_VERSIONINFO` (product name, publisher, version)
- **.NET / CLR detection** - via the COM descriptor data directory
- **Application classification** - conservatively distinguishes games from ordinary applications using Steam, engine, graphics, and input signals
- **Anti-cheat detection** - warns about Easy Anti-Cheat and BattlEye without treating per-title Proton support as a guaranteed failure
- **Compatibility reporting** - one consolidated report: recommended backend, required Winetricks verbs, blocking issues, and notes
- **Host detection** - checks host architecture, Wine and Winetricks availability/version
- **Proton discovery** - finds Valve, Experimental, GE, custom, Flatpak, Snap, and additional Steam-library installations
- **Real Proton execution** - creates isolated compat data and invokes Proton with its required Steam compatibility environment
- **Runtime control** - `--backend`, `--proton`, and `runexe backends` make selection predictable and inspectable
- **Wine prefix management** - creates and reuses a stable, per-app prefix automatically
- **Winetricks integration** - installs required runtimes (VC++ redistributables, D3D compiler/extension libs, OpenAL, .NET Framework) before launch
- **Native Wine execution** - launches from the application directory and preserves arguments, stdout, stderr, timeouts, and exit codes
- **Polished terminal UI** - readable launch plans, compact tables, clear status language, and a terminal mark derived from the project logo
- **Automation-friendly reports** - emits the full analysis and compatibility result as JSON

## 📋 Requirements

- Linux on an x86 or x86_64 host
- Python 3.10+
- [Wine](https://www.winehq.org/), [Proton](https://github.com/ValveSoftware/Proton), or both (`analyze --no-host` needs neither)
- [Winetricks](https://github.com/Winetricks/winetricks) (optional, but needed for automatic dependency installation)

## 🔧 Installation

```bash
git clone https://github.com/cdjuaum/runexe.git
cd runexe
pip install -e .
```

This installs the `runexe` command via [Typer](https://typer.tiangolo.com/).

## 📖 Usage

**Analyze an executable** - inspect it without running anything:

```bash
runexe analyze path/to/app.exe
```

AppX/MSIX packages and unpacked package directories are also supported. RunEXE
reads the package manifest, safely materializes the declared executable, and
launches that executable directly through the selected compatibility runtime:

```bash
runexe analyze Paint.msix
runexe run Paint.msix --no-deps
```

Add `--imports` / `-i` to list every imported function per DLL, not just counts:

```bash
runexe analyze path/to/app.exe --imports
```

Emit JSON for scripts, CI, or other tooling, or skip host checks for a purely static report:

```bash
runexe analyze path/to/app.exe --json
runexe analyze path/to/app.exe --no-host
```

**Run software** - analyze it, select Wine or Proton, prepare an isolated environment, and launch:

```bash
runexe run path/to/app.exe
```

Useful flags:

```bash
runexe run path/to/app.exe --verbose        # show prefix/backend/launch details
runexe run path/to/app.exe --timeout 60     # give up after 60s
runexe run path/to/app.exe --winver 10      # report Windows 10 to the app
runexe run path/to/app.exe --no-deps         # do not invoke Winetricks
runexe run path/to/app.exe --backend wine
runexe run path/to/game.exe --backend proton
runexe run path/to/game.exe --proton "Proton Experimental"
runexe run path/to/game.exe --proton ~/.steam/root/compatibilitytools.d/GE-Proton/proton
```

Inspect what is installed and the order in which Proton builds will be selected:

```bash
runexe backends
```

`--backend auto` is the default. It prefers Proton for detected games and Wine
for regular applications, then falls back to whichever runtime is available.
`--proton` implies the Proton backend. `RUNEXE_PROTON_PATH` can point to a custom
Proton directory or launcher that is outside Steam's normal locations.

Pass arguments to the Windows application after `--`:

```bash
runexe run path/to/app.exe -- --portable "C:\\data file.txt"
```

Wine prefixes live under `$XDG_DATA_HOME/runexe/prefixes`; Proton compat data
lives under `$XDG_DATA_HOME/runexe/proton`. `--prefix` overrides the relevant
location for either backend. Wine dependency provisioning is automatic. Proton
dependency changes are opt-in with `--deps` because modifying a
game-focused Proton prefix can reduce compatibility.

**Check the installed version:**

```bash
runexe version
```

## 🗺️ Roadmap

### v0.3.x

- [x] PE executable analysis
- [x] Architecture detection
- [x] Import analysis
- [x] .NET detection
- [x] Compatibility reporting
- [x] Host detection
- [x] Wine detection
- [x] Wine prefix management
- [x] Winetricks integration
- [x] Native Wine execution
- [x] Improve 32-bit Wine capability detection
- [x] Proton backend
- [x] Steam and custom Proton discovery
- [x] Automatic Proton environment configuration
- [x] AppX/MSIX inspection and launch support
- [x] Rich terminal UI and coordinated project identity
- [ ] More Windows runtime detection
- [ ] Better DirectX dependency detection
- [ ] GPU/Vulkan capability detection
- [ ] DXVK detection
- [ ] More robust application classification
- [ ] Improved Wine configuration

### Future

- [ ] Launch existing Steam titles by App ID
- [ ] More advanced compatibility scoring
- [ ] GUI
- [ ] Application database / community compatibility data

## 🛡️ Notes

- RunEXE does not modify the analyzed executable in any way - analysis is read-only.
- `runexe analyze` does not initialize Wine prefixes or otherwise mutate Wine state.
- AppX/MSIX archives are extracted into `$XDG_CACHE_HOME/runexe/packages` (or `~/.cache/runexe/packages`) for reuse. Package signatures are not verified; only run packages you trust.
- Package identity and Microsoft Store services are not recreated. Classic Win32 applications distributed inside AppX/MSIX may work, while UWP/Store-only features may still fail under Wine.
- Wine is a compatibility layer, **not a security sandbox**. Only run executables you trust; use a VM or a dedicated sandbox for untrusted software.
- Anti-cheat detection is a best-effort signal based on known import names (see `constants.py`); it is not exhaustive and deliberately does not attempt to detect wrapper/VM-based DRM such as Denuvo. [Proton support for EAC and BattlEye is enabled per title](https://partner.steamgames.com/doc/steamhardware/proton), so these detections are warnings rather than automatic blockers.
- Game detection is heuristic. Use `--backend wine` or `--backend proton` whenever you know which runtime the application needs.
- RunEXE launches Proton directly through its `proton run` interface with isolated compat data. Valve primarily designs Proton for use through Steam, so a particular title may still depend on Steam runtime services or launch configuration.
- Provided "AS IS" without warranty of any kind.

## 🤝 Contributing

Contributions are welcome! Feel free to open an issue or submit a Pull Request.

Install the development tools and run the full local verification suite:

```bash
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
pytest
python -m build
```

## 📄 License

This project is licensed under the **LGPL-2.1** License - see the [LICENSE](LICENSE) file for details.

## 💬 Support

For support or questions, please open an issue on GitHub.
