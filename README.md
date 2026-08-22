# RunEXE

Analyze Windows executables and run them on Linux through Wine - with automatic compatibility detection, anti-cheat/DRM flagging, and dependency provisioning.

![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![License](https://img.shields.io/badge/license-LGPL--2.1-green) ![Status](https://img.shields.io/badge/status-early--development-orange)

RunEXE inspects a Windows `.exe` (architecture, imports, subsystem, embedded manifest, version info, .NET/CLR header) and turns that into a concrete compatibility report: which backend to use, which Winetricks dependencies to install, and any known blockers (like kernel-level anti-cheat) before you ever try to launch it. Point it at a prefix-less executable and it'll create the Wine prefix, install what's needed, and run it - no manual `winecfg` required for straightforward apps.

## ✅ Tested Applications

The following have been run through RunEXE with **no additional setup** beyond what the tool provisions automatically:

- Notepad++
- PuTTY.exe

More compatibility data is one of the long-term goals of the project (see [Roadmap](#-roadmap)).

## 🚀 Features

- **PE analysis** - parses the executable directly (no Wine required just to inspect a file)
- **Architecture detection** - x86 / x86_64 / ARM64, mapped to the correct `WINEARCH`
- **Import table analysis** - full DLL + function listing (`--imports`)
- **Subsystem parsing** - Windows GUI vs. Console vs. others
- **Embedded manifest extraction** - reads `RT_MANIFEST`, surfaces the requested execution level (e.g. `requireAdministrator`)
- **Version info parsing** - `VS_VERSIONINFO` (product name, publisher, version)
- **.NET / CLR detection** - via the COM descriptor data directory
- **Application classification** - distinguishes games from ordinary applications using Steam API and graphics/input middleware import signals
- **Anti-cheat detection** - flags known kernel-level anti-cheat clients (Easy Anti-Cheat, BattlEye) as blocking issues before launch is attempted
- **Compatibility reporting** - one consolidated report: recommended backend, required Winetricks verbs, blocking issues, and notes
- **Host detection** - checks host architecture, Wine and Winetricks availability/version
- **Wine prefix management** - creates and reuses a stable, per-app prefix automatically
- **Winetricks integration** - installs required runtimes (VC++ redistributables, D3D compiler/extension libs, OpenAL, .NET Framework) before launch
- **Native Wine execution** - launches the target executable and captures stdout/stderr/exit code

## 📋 Requirements

- Python 3.11+
- [Wine](https://www.winehq.org/) (required to create prefixes and run executables - not required for `analyze`)
- [Winetricks](https://github.com/Winetricks/winetricks) (optional, but needed for automatic dependency installation)

## 🔧 Installation

```bash
git clone https://github.com/<your-username>/runexe.git
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

**Run an executable** - analyze, provision a Wine prefix, install any required dependencies, and launch:

```bash
runexe run path/to/app.exe
```

Useful flags:

```bash
runexe run path/to/app.exe --verbose        # show prefix/backend/launch details
runexe run path/to/app.exe --timeout 60     # give up after 60s
```

**Check the installed version:**

```bash
runexe version
```

## 🗺️ Roadmap

### v0.1.x

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
- [ ] Improve 32-bit Wine capability detection
- [ ] Expand dependency detection
- [ ] Improve compatibility reporting

### v0.2.x

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
- Anti-cheat detection is a best-effort signal based on known import names (see `constants.py`); it is not exhaustive and deliberately does not attempt to detect wrapper/VM-based DRM such as Denuvo.
- Provided "AS IS" without warranty of any kind.

## 🤝 Contributing

Contributions are welcome! Feel free to open an issue or submit a Pull Request.

## 📄 License

This project is licensed under the **LGPL-2.1** License - see the [LICENSE](LICENSE) file for details.

## 💬 Support

For support or questions, please open an issue on GitHub.
