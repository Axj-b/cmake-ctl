# cmake-ctl

A CMake version manager with a transparent `cmake` proxy, project-aware resolution, and safe cleanup tooling.

`cmake-ctl` lets you install multiple CMake versions side-by-side and route `cmake` calls to the right version without changing your build commands.

## Highlights

- Install CMake versions from URL or local archive
- Switch versions globally, per project, or per session
- Transparent proxy executable for normal `cmake` workflows
- Event logging and project tracking
- Safe cleanup with dry-run support and pin-aware behavior
- Interactive TUI for common workflows

## Repository Layout

```text
.
├── bin/
│   ├── cmake.exe            # C++ proxy executable (Windows)
│   └── cmake-ctl.bat         # CLI entrypoint wrapper
├── cmakectl/
│   ├── src/cmake_ctl/        # Python package
│   └── tests/               # Unit tests
├── src/proxy/
│   └── proxy.cpp            # C++ proxy source
├── docs/
│   ├── IDEA.md
│   └── V1-CHECKLIST.md
├── CMakeLists.txt           # Proxy build definition
├── build.bat
├── build.sh
└── README.md
```

## Runtime Data Location

By default, runtime state is stored in:

- Windows: `C:\Users\<you>\.cmake-ctl`
- Override with: `CMAKE_CTL_HOME`

Inside that directory:

- `config.json` - global and per-project settings
- `versions/` - installed CMake versions
- `events/` - proxy invocation logs
- `projects.db` - tracked project metadata
- `downloads/` - downloaded archives

## Quick Start (Windows)

### 1. Use the CLI from repo

```powershell
cd ~/.cmake-ctl\cmakectl
$env:PYTHONPATH = "src;tests"
python -m cmake_ctl.cli list
```

### 2. Install a CMake version

From URL only:

```powershell
python -m cmake_ctl.cli install 3.30.0 --url "https://github.com/Kitware/CMake/releases/download/v3.30.0/cmake-3.30.0-windows-x86_64.zip"
```

From local archive:

```powershell
python -m cmake_ctl.cli install-archive 4.3.1 --archive "~/.cmake-ctl\archive\cmake-4.3.1-windows-x86_64.zip"
```

### 3. Select active version

```powershell
python -m cmake_ctl.cli use 3.30.0
python -m cmake_ctl.cli resolve
```

### 4. Route `cmake` through proxy

```powershell
$env:PATH = "~/.cmake-ctl\bin;$env:PATH"
cmake --version
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

## Resolution Priority

Version resolution follows this order:

1. Explicit command override
2. Session override
3. Project-persistent mapping
4. `.cmake-version` in project
5. Global default (`config.json`)
6. Latest installed version

## Build the Proxy

```powershell
cd ~/.cmake-ctl
.\build.bat
```

This builds `cmake-ctl-proxy.exe` into `build\Release` and deploys as `bin\cmake.exe`.

## Testing

```powershell
cd ~/.cmake-ctl\cmakectl
$env:PYTHONPATH = "src;tests"
python -m unittest discover -s tests -v
```

## Notes and Safety

- URL install without `--manifest`/`--sha256` is allowed but not checksum-verified.
- `clean` defaults to preview mode unless `--execute` is provided.
- Proxy recursion is guarded to avoid self-invocation loops.

## License

No license file is currently defined in this repository.
