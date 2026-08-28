# RunEXE

Analyze Windows executables and run them on Linux through Wine - with automatic compatibility detection, anti-cheat warnings, and dependency provisioning.

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![License](https://img.shields.io/badge/license-LGPL--2.1-green) ![Status](https://img.shields.io/badge/status-alpha-orange)

RunEXE inspects a Windows `.exe` (architecture, imports, subsystem, embedded manifest, version info, .NET/CLR header) and turns that into a concrete compatibility report: which backend to use, which Winetricks dependencies to install, and any known blockers (like kernel-level anti-cheat) before you ever try to launch it. Point it at a prefix-less executable and it'll create the Wine prefix, install what's needed, and run it - no manual `winecfg` required for straightforward apps.

## ✅ Tested Applications

The following have been run through RunEXE with **no additional setup** beyond what the tool provisions automatically:

- Notepad++ (Native)
- Notepad++ (32-bit)
- PuTTY.exe (Native)
- KeePass (.NET)

More compatibility data is one of the long-term goals of the project (see [Roadmap](#-roadmap)).

## 🚀 Features

- **Defensive PE analysis** - bounded, read-only parsing of file-backed PE data (Wine is not required)
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
- **Wine prefix management** - creates and reuses a stable, per-app prefix automatically
- **Winetricks integration** - installs required runtimes (VC++ redistributables, D3D compiler/extension libs, OpenAL, .NET Framework) before launch
- **Native Wine execution** - launches from the application directory and preserves arguments, stdout, stderr, timeouts, and exit codes
- **Automation-friendly reports** - emits the full analysis and compatibility result as JSON

## 📋 Requirements

- Linux on an x86 or x86_64 host
- Python 3.10+
- [Wine](https://www.winehq.org/) (required to create prefixes and run executables - not required for `analyze`)
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

Add `--imports` / `-i` to list every imported function per DLL, not just counts:

```bash
runexe analyze path/to/app.exe --imports
```

Emit JSON for scripts, CI, or other tooling, or skip host checks for a purely static report:

```bash
runexe analyze path/to/app.exe --json
runexe analyze path/to/app.exe --no-host
```

**Run an executable** - analyze, provision a Wine prefix, install any required dependencies, and launch:

```bash
runexe run path/to/app.exe
```

Useful flags:

```bash
runexe run path/to/app.exe --verbose        # show prefix/backend/launch details
runexe run path/to/app.exe --timeout 60     # give up after 60s
runexe run path/to/app.exe --winver 10      # report Windows 10 to the app
runexe run path/to/app.exe --no-dependencies # do not invoke Winetricks
runexe run path/to/app.exe --prefix ~/.wine-my-app
```

Pass arguments to the Windows application after `--`:

```bash
runexe run path/to/app.exe -- --portable "C:\\data file.txt"
```

RunEXE reuses a deterministic per-application prefix under
`$XDG_DATA_HOME/runexe/prefixes` (or `~/.local/share/runexe/prefixes`). A custom
`--prefix` is validated to avoid silently reusing a prefix with the wrong
architecture.

**Check the installed version:**

```bash
runexe version
```

## 🗺️ Roadmap

### v0.2.x

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
- [ ] More Windows runtime detection
- [ ] Better DirectX dependency detection
- [ ] GPU/Vulkan capability detection
- [ ] DXVK detection
- [ ] More robust application classification
- [ ] Improved Wine configuration

### Future

- [ ] Proton backend
- [ ] Steam integration
- [ ] Automatic Proton environment configuration
- [ ] More advanced compatibility scoring
- [ ] GUI
- [ ] Application database / community compatibility data

## 🛡️ Notes

- RunEXE does not modify the analyzed executable in any way - analysis is read-only.
- `runexe analyze` does not initialize Wine prefixes or otherwise mutate Wine state.
- Wine is a compatibility layer, **not a security sandbox**. Only run executables you trust; use a VM or a dedicated sandbox for untrusted software.
- Anti-cheat detection is a best-effort signal based on known import names (see `constants.py`); it is not exhaustive and deliberately does not attempt to detect wrapper/VM-based DRM such as Denuvo. [Proton support for EAC and BattlEye is enabled per title](https://partner.steamgames.com/doc/steamhardware/proton), so these detections are warnings rather than automatic blockers.
- Game detection is heuristic. Until Proton provisioning is implemented, RunEXE launches supported games with Wine while noting that Proton may work better.
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
