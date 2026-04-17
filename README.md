# cmake-ctl

cmake-ctl is a CMake version manager with a transparent `cmake` proxy, project-aware resolution, and cleanup tooling.

It lets you install multiple CMake versions side-by-side and keep normal `cmake` commands while routing to the right version.

## Highlights

- Install CMake versions from URL or local archive
- Resolve versions globally, per project, or per session
- Transparent proxy executable (`cmake`/`cmake.exe`)
- Event logging and tracked project metadata
- Safe cleanup with dry-run and pin-aware behavior
- CLI + interactive TUI workflows

## Real Repository Structure

```text
.
├── bin/                         # Runtime entrypoints and proxy artifact
│   ├── cmake.exe               # Proxy artifact on Windows (cmake on Unix)
│   └── cmake-ctl.bat           # CLI launcher (Windows)
├── build/                       # CMake build directory (generated)
├── cmakectl/
│   ├── pyproject.toml
│   ├── src/
│   │   └── cmake_ctl/          # Python package source
│   │       ├── cli.py
│   │       ├── resolver.py
│   │       ├── installer.py
│   │       ├── events.py
│   │       ├── database.py
│   │       └── ...
│   └── tests/                  # Python unit tests
├── docs/
│   ├── IDEA.md
│   └── V1-CHECKLIST.md
├── proxy/
│   ├── CMakeLists.txt          # Canonical proxy CMake definition
│   └── src/
│       └── proxy/
│           └── proxy.cpp       # C++ proxy source
├── scripts/
│   └── create_release_zip.py   # End-user zip packaging script
├── dist/                        # Release zips (generated)
├── CMakeLists.txt               # Top-level wrapper (add_subdirectory(proxy))
├── build.bat                    # Windows build entrypoint
├── build.sh                     # Linux/macOS build entrypoint
├── INSTALLATION.md
└── README.md
```

Notes:
- Build definitions are under `proxy/`, not `bin/`.

## Runtime Data Location

By default, runtime state is stored in:

- Windows: `C:\Users\<you>\.cmake-ctl`
- Linux/macOS: `~/.cmake-ctl`
- Override with environment variable: `CMAKE_CTL_HOME`

Typical contents:

- `config.json`: global and per-project config
- `versions/`: installed CMake versions
- `events.log`: canonical event queue
- `events/cmake_invocations.ndjson`: legacy queue input (still supported)
- `projects.db`: tracked project metadata
- `downloads/`: downloaded archives

## Build Proxy

### Windows

```powershell
cd ~/.cmake-ctl
.\build.bat
```

### Linux/macOS

```bash
cd /path/to/cmakectl
./build.sh
```

Build output:

- Windows: `bin/cmake.exe`
- Linux/macOS: `bin/cmake`

Fallback behavior:

- Scripts use CMake when available.
- If CMake is not available (or fails), they fall back to direct compiler builds.
  - Windows fallback order: `cl`, `clang++`, `g++`
  - Linux/macOS fallback order: `c++`, `g++`, `clang++`

## Use CLI From Source Checkout

### Windows PowerShell

```powershell
cd ~/.cmake-ctl\cmakectl
$env:PYTHONPATH = "src;tests"
python -m cmake_ctl.cli list
```

### Linux/macOS

```bash
cd /path/to/cmakectl/cmakectl
export PYTHONPATH="src:tests"
python -m cmake_ctl.cli list
```

## Core Commands

```text
cmake-ctl use <version> [--project <path>] [--session]
cmake-ctl resolve [--project <path>] [cmake args...]
cmake-ctl install <version> --url <url> [--manifest <file>] [--sha256 <hash>]
cmake-ctl install-archive <version> --archive <file>
cmake-ctl list
cmake-ctl events --process
cmake-ctl projects [--pin <key> | --unpin <key>]
cmake-ctl clean [--project <path>] [--build-dir <dir>] [--archive-dir <dir>] [--execute] [--pinned]
cmake-ctl proxy-run -- <cmake args...>
cmake-ctl show-config [--json]
cmake-ctl identity-mode [id-file-first|path-only]
cmake-ctl tui
```

## Version Resolution Priority

1. Explicit command override
2. Session override
3. Project-persistent mapping
4. `.cmake-version` in project
5. Global default (`config.json`)
6. Latest installed version

## Create End-User Release Zip

Use the packaging script:

```powershell
cd ~/.cmake-ctl
python scripts/create_release_zip.py --version 0.1.0
```

Example output:

```text
dist/cmake-ctl-0.1.0-windows-x64.zip
```

Useful options:

- `--skip-build`: package existing artifacts only
- `--platform`: override platform label
- `--out-dir`: output directory (default `dist`)

Minimal GitHub Actions step:

```yaml
- name: Create release zip
  run: python scripts/create_release_zip.py --version ${{ github.ref_name }}
```

## Testing

### Windows PowerShell

```powershell
cd ~/.cmake-ctl\cmakectl
$env:PYTHONPATH = "src;tests"
python -m unittest discover -s tests -v
```

### Linux/macOS

```bash
cd /path/to/cmakectl/cmakectl
export PYTHONPATH="src:tests"
python -m unittest discover -s tests -v
```

## Notes

- URL install without `--manifest` or `--sha256` is allowed but not checksum-verified.
- `clean` defaults to preview mode unless `--execute` is provided.
- Proxy recursion protection is enabled.

## License

No license file is currently defined in this repository.
