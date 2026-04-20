# cmake-ctl

cmake-ctl is a CMake version manager with a transparent `cmake` proxy, project-aware resolution, interactive TUI, and cleanup tooling.

It lets you install multiple CMake versions side-by-side and keep normal `cmake` commands while routing to the right version.

## Highlights

- Install CMake versions from URL or local archive
- Resolve versions globally, per project, or per session
- Transparent proxy executables (`cmake`, `ctest`, `cpack`, `ccmake`, `cmake-gui`; plus `cmcldeps.exe` on Windows) — drop-in replacement
- Automatic fallback to global/latest version if configured version is missing
- Event logging and tracked project metadata (auto-populated by proxy)
- Safe cleanup with interactive target selection, dry-run, and pin-aware behavior
- Remove installed versions and clear the downloads cache
- VSCode CMake Tools integration — auto-configure `cmake.cmakePath`
- Setup scripts for PATH and VSCode on Windows and Linux/macOS
- Colorful interactive TUI with arrow-key navigation

## Real Repository Structure

```text
.
├── bin/                         # Runtime entrypoints and proxy artifact
│   ├── cmake.exe               # Proxy artifact on Windows (cmake on Unix)
│   ├── ctest(.exe)             # Companion proxy executable
│   ├── cpack(.exe)             # Companion proxy executable
│   ├── ccmake(.exe)            # Companion proxy executable
│   ├── cmake-gui(.exe)         # Companion proxy executable
│   └── cmcldeps.exe            # Companion proxy executable (Windows)
│   └── cmake-ctl.bat           # CLI launcher (Windows)
├── cmake-ctl/
│   ├── pyproject.toml
│   ├── src/
│   │   └── cmake-ctl/          # Python package source
│   │       ├── cli.py
│   │       ├── resolver.py
│   │       ├── installer.py
│   │       ├── events.py
│   │       ├── database.py
│   │       ├── tui.py
│   │       ├── vscode_setup.py
│   │       └── ...
│   └── tests/                  # Python unit tests
├── proxy/
│   ├── CMakeLists.txt
│   └── src/proxy/proxy.cpp     # C++ proxy source
├── scripts/
│   ├── create_release_folder.py # End-user release folder staging script
│   └── create_release_zip.py    # End-user zip packaging script
├── dist/                        # Staged releases and zip artifacts (generated)
├── CMakeLists.txt
├── build.bat                    # Windows build entrypoint
├── build.sh                     # Linux/macOS build entrypoint
├── setup.ps1                    # Windows one-shot setup (PATH + VSCode)
├── setup.sh                     # Linux/macOS one-shot setup (PATH + VSCode)
├── INSTALLATION.md
└── README.md
```

## Quick Setup

### Windows (PowerShell)

```powershell
# Add bin\ to your User PATH (and optionally configure VSCode)
.\setup.ps1
.\setup.ps1 -VSCode        # also writes cmake.cmakePath to VSCode settings
.\setup.ps1 -Uninstall     # undo
```

### Linux/macOS

```bash
./setup.sh
./setup.sh --vscode
./setup.sh --uninstall
```

The scripts auto-detect standard and Scoop VSCode installs.

## Runtime Data Location

By default, runtime state is stored in:

- Windows: `C:\Users\<you>\.cmake-ctl`
- Linux/macOS: `~/.cmake-ctl`
- Override with: `CMAKE_CTL_HOME=<path>`

Typical contents:

| Path | Purpose |
|------|---------|
| `config.json` | Global and per-project config |
| `versions/` | Installed CMake versions |
| `events.log` | Canonical event queue |
| `projects.db` | Tracked project metadata |
| `downloads/` | Downloaded archives |

## Build Proxy

### Windows

```powershell
.\build.bat
```

### Linux/macOS

```bash
./build.sh
```

Output: `bin/cmake(.exe)` plus companion proxies for `ctest`, `cpack`, `ccmake`, `cmake-gui` (and `cmcldeps.exe` on Windows).

Compiler fallback (when CMake is not available):
- Windows: `cl` → `clang++` → `g++`
- Linux/macOS: `c++` → `g++` → `clang++`

## Use CLI From Source

### Windows PowerShell

```powershell
cd cmake-ctl
$env:PYTHONPATH = "src;tests"
python -m cmake-ctl.cli list
```

### Linux/macOS

```bash
cd cmake-ctl
export PYTHONPATH="src:tests"
python -m cmake-ctl.cli list
```

## Core Commands

```text
cmake-ctl use <version> [--project <path>] [--session]
cmake-ctl resolve [--project <path>] [cmake args...]
cmake-ctl install <version> [--url <url>] [--manifest <file>] [--sha256 <hash>]
cmake-ctl install-archive <version> --archive <file>
cmake-ctl list
cmake-ctl uninstall [version] [--yes]
cmake-ctl clear-downloads
cmake-ctl events --process
cmake-ctl projects [--pin <id-or-key> | --unpin <id-or-key> | --remove <id-or-key> | --prune-missing]
cmake-ctl clean [<project-path-or-id>] [--project <path>] [--build-dir <dir>] [--archive-dir <dir>] [--execute] [--pinned]
cmake-ctl proxy-run -- <cmake args...>
cmake-ctl show-config [--json]
cmake-ctl identity-mode [id-file-first|path-only]
cmake-ctl setup-vscode [--settings <path>] [--remove]
cmake-ctl tui
```

## Version Resolution Priority

1. Explicit command override
2. Session override
3. Project-persistent mapping
4. `.cmake-version` file in project root
5. Global default (`config.json`)
6. Latest installed version

**Fallback behavior:** if the resolved version's binary is missing (e.g. after `uninstall`), the proxy automatically falls back to the global configured version, then to the latest installed version, emitting a warning. It only errors if nothing usable is found.

## VSCode Integration

Point VSCode CMake Tools at the proxy to track all cmake invocations:

```powershell
cmake-ctl setup-vscode          # auto-detect VSCode settings and write cmake.cmakePath
cmake-ctl setup-vscode --remove # revert
```

Or use the setup script: `.\setup.ps1 -VSCode`.

This sets `cmake.cmakePath` in your VSCode user `settings.json` globally, so all workspaces use the proxy.

## Interactive TUI

```text
cmake-ctl tui
```

Available TUI commands (type `/command`):

| Command | Description |
|---------|-------------|
| `/list` | Select and set global version (arrow keys); press `d` to delete |
| `/uninstall` | Interactive version removal |
| `/clear-downloads` | Wipe download cache |
| `/install` | Install from URL with progress |
| `/install-archive` | Install from local archive |
| `/use` | Set version (global / project / session) |
| `/resolve` | Show resolved version for a path |
| `/events` | Process proxy event queue |
| `/projects` | List/pin/unpin tracked projects |
| `/clean` | Interactive cleanup — pick from tracked projects or custom path |
| `/proxy-run` | Forward cmake invocation through proxy |
| `/show-config` | Display current configuration |
| `/setup-vscode` | Configure VSCode cmake path |
| `/identity-mode` | Get or set project identity mode |
| `/help` | List all commands |
| `/exit` or `/q` | Quit |

The `/clean` command lets you pick from your tracked projects list, then select individual build directories to delete with arrow keys and space bar.

CLI shortcut: use a tracked project ID from `cmake-ctl projects` directly, for example `cmake-ctl clean 2`.

Maintenance shortcuts:
- `cmake-ctl projects --pin <id-or-key>` pins one tracked project entry.
- `cmake-ctl projects --unpin <id-or-key>` unpins one tracked project entry.
- `cmake-ctl projects --remove <id-or-key>` removes one tracked project entry.
- `cmake-ctl projects --prune-missing` removes entries whose project paths no longer exist.

## Create End-User Release Zip

First stage the uncompressed release folder (useful for CI/CD assets that do not need zip):

```powershell
python scripts/create_release_folder.py --version 0.1.0
```

Output: `dist/cmake-ctl-0.1.0-windows-x64/`

If build tools are unavailable, the script automatically reuses an already-built
proxy from `bin/` when present.

Then create the zip when needed:

```powershell
python scripts/create_release_zip.py --version 0.1.0
```

Output: `dist/cmake-ctl-0.1.0-windows-x64.zip`

The zip includes `setup.ps1` and `setup.sh` so end-users can run setup immediately after extracting.

Options:
- `--skip-build`: package existing artifacts only
- `--platform`: override platform label
- `--out-dir`: output directory (default `dist`)

GitHub Actions step:

```yaml
- name: Create release zip
  run: python scripts/create_release_zip.py --version ${{ github.ref_name }}
```

## Testing

```powershell
# Windows
cd cmake-ctl
$env:PYTHONPATH = "src;tests"
python -m unittest discover -s tests -v
```

```bash
# Linux/macOS
cd cmake-ctl
export PYTHONPATH="src:tests"
python -m unittest discover -s tests -v
```

## Notes

- `install` without `--manifest` or `--sha256` is allowed but skips checksum verification.
- `clean` defaults to preview/dry-run unless `--execute` is provided (or confirmed in TUI).
- Proxy recursion protection is always enabled.
- `CMAKE_CTL_HOME` overrides all data directory paths.

## License

No license file is currently defined in this repository.
