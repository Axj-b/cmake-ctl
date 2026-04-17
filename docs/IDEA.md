# CMake Control Center - Project Summary

## Overview
CMake Control Center is a unified tool that combines CMake version management with automatic project tracking.

It solves two common problems:
- Managing multiple CMake versions reliably
- Tracking and cleaning build artifacts that consume disk space

## Architecture

### Component 1: C++ Proxy (cmake.exe)
Purpose: lightweight shim that intercepts all cmake calls.

Targets:
- Size: about 500 KB compiled
- Startup overhead: less than 10 ms

Responsibilities:
- Intercept cmake commands transparently
- Route to the correct CMake version
- Log events to a queue file in a non-blocking way
- Pass through all arguments unchanged
- Return the same exit code as real CMake

### Component 2: Python Tool (cmakectl)
Purpose: feature-rich management and tracking tool.

Responsibilities:
- Download and install CMake versions
- Manage version switching globally, per project, and per session
- Process event queue data from the proxy
- Track projects in SQLite
- Calculate project sizes in the background
- Clean build artifacts
- Generate statistics and recommendations
- Provide a polished CLI and TUI experience

## Core Features

### Version Management
- Install multiple CMake versions side-by-side
- Switch versions globally, per project, or for current session only
- Auto-detect version from .cmake-version
- Download versions from cmake.org
- Remove unused versions

Version preference modes:
- Global default: applies when no project or session override exists
- Project-persistent: remembered for a project so next time no manual switching is needed
- Session-only: temporary override for the current shell session

Project identity and moved folder behavior:
- Configurable identity strategy:
  - id-file-first: use .cmakectl/project-id and fall back to canonical path
  - path-only: use canonical path only
- If a project is moved and project-id is present, mapping can follow the project to the new path
- If project-id is missing, path fallback treats moved location as a new project unless user remaps

### Project Tracking
- Auto-register projects when cmake runs
- Track metadata: size, last modified, CMake version, generator
- Categorize by age:
  - Active: 0 to 7 days
  - Stale: 7 to 30 days
  - Abandoned: 30+ days
- Compare build artifact size vs source size
- Tag and annotate projects
- Pin important projects

### Cleanup and Management
- Identify cleanable artifacts (for example build outputs, bin, obj, packages)
- One-command cleanup for stale projects
- Dry-run preview before deletion
- Recommendations for likely space savings
- Archive old projects

### Statistics and Insights
- Total disk usage across tracked projects
- Usage by CMake version
- Usage by generator (Visual Studio, Ninja, and others)
- Activity trends over time
- Cleanup potential estimates

### Interactive TUI
- Launch a guided terminal UI with `cmakectl tui`
- Friendly onboarding for new users with plain-language actions
- Quick workflows for install, use, projects, clean, and stats
- Context panel showing active global, project, and session version sources
- Safe actions by default: previews and confirmations for destructive operations

## Directory Structure

```text
C:\Tools\cmakectl
├── cmake.exe                   # C++ proxy
├── cmakectl\                   # Python package
│   ├── main.py                 # Entry point
│   ├── cli.py                  # Click commands
│   ├── version_manager.py      # Version handling
│   ├── project_tracker.py      # Project database logic
│   ├── cleaner.py              # Artifact cleanup
│   ├── stats.py                # Statistics
│   └── utils.py                # Helpers
├── versions\                   # Installed CMake versions
│   ├── 3.28.1
│   ├── 3.27.0
│   └── 3.26.4
├── config.json                 # Configuration
├── projects.db                 # SQLite database
└── events.log                  # Event queue from proxy
```

## Command Examples

### Version Management
```bash
cmakectl install 3.28.1
cmakectl list
cmakectl use 3.28.1
cmakectl use 3.27.0 --project .
cmakectl use 3.27.0 --session
cmakectl remove 3.26.4
cmakectl update
cmakectl tui
```

### Project Management
```bash
cmakectl projects
cmakectl projects --active
cmakectl projects --stale
cmakectl info
cmakectl clean
cmakectl clean --all-stale
cmakectl clean --dry-run
cmakectl tag work client-a
cmakectl note "Important client"
cmakectl pin
cmakectl stats
cmakectl analyze
```

## Data Tracked Per Project

```json
{
  "id": "uuid",
  "name": "MyProject",
  "path": "C:/Dev/MyProject",
  "sourceDir": "C:/Dev/MyProject",
  "buildDir": "C:/Dev/MyProject/build",
  "cmakeVersion": "3.28.1",
  "generator": "Visual Studio 17 2022",
  "created": "2024-01-15T10:30:00Z",
  "lastConfigured": "2024-01-20T14:22:00Z",
  "configureCount": 15,
  "totalSize": 2147483648,
  "buildArtifactsSize": 1932735283,
  "sourceSize": 214748365,
  "status": "active",
  "tags": ["work", "cpp"],
  "notes": "Client project - important",
  "pinned": false
}
```

## How It Works

### Transparent Interception Flow
1. User runs: cmake -G "Visual Studio 17 2022" ..
2. C++ proxy intercepts the call.
3. Proxy determines the CMake version to run.
4. Proxy logs an event to events.log.
5. Proxy executes real cmake with unchanged arguments.
6. Proxy returns the same exit code to the caller.
7. Python tool processes events in the background.
8. Project record is created or updated in SQLite.
9. If global version changed earlier, open terminals use the new global value on their next cmake invocation without restart.

### Version Detection Priority
1. Explicit override from command context
2. Session override (`cmakectl use <ver> --session`)
3. Project-persistent mapping
4. .cmake-version in project root
5. Global default in config.json
6. Latest installed version

## Implementation Phases

### Phase 1: C++ Proxy
- Basic cmake.exe proxy
- Argument pass-through
- Version routing logic
- Event logging
- Cross-platform support (Windows and Linux)

### Phase 2: Python Tool Core
- CLI framework with Click
- Version discovery and download
- Installation and extraction
- Configuration management
- Base commands: install, list, use, tui
- Session override storage and lifecycle

### Phase 3: Project Tracking
- SQLite schema and migrations
- Event queue processing
- Project registration and update flow
- Background size calculation
- List and filter commands
- Project identity strategy (id-file-first and path-only)
- Moved-path reconciliation behavior

### Phase 4: Cleanup and Management
- Build artifact detection
- Clean commands
- Tagging and notes
- Statistics generation
- Recommendations engine

### Phase 5: Polish
- Rich terminal output
- TUI usability polish and onboarding flows
- Interactive prompts
- Setup wizard
- Auto-update checks
- Documentation

## Technology Stack

### C++ Proxy
- Language: C++17
- Dependencies: standard library only
- Optional: nlohmann/json (header-only)
- Build system: CMake

### Python Tool
- Language: Python 3.8+
- Core libraries:
  - click
  - rich
  - textual (for TUI)
  - requests
  - sqlite3 (built-in)
  - pathlib (built-in)
- Distribution: PyInstaller standalone bundle

## Distribution

### For Developers
- Python package install: pip install cmakectl
- Includes compiled cmake.exe proxy
- Source code available

### For End Users
- Standalone PyInstaller bundle
- Single download with both components
- No Python required
- Installer can add toolchain paths

## Key Benefits

### Solves Real Problems
- Eliminates manual CMake version switching
- Reduces disk waste from abandoned build artifacts
- Makes CMake project usage visible
- Automates cleanup decisions
- Keeps workflow transparent

### Technical Advantages
- Fast proxy startup
- Complex logic stays in maintainable Python code
- Cross-platform support target (Windows and Linux)
- No edits required to CMakeLists.txt or presets
- Works with CLI, IDE, and scripts

### User Experience
- Clear CLI output
- Guided TUI for discoverability and first-use success
- Actionable recommendations
- One-command cleanup flows
- Useful statistics and trend visibility
- Flexible tagging and organization

## Future Enhancements

### Potential Features
- Background daemon for monitoring
- Notifications for stale projects
- Multi-project workspace support
- Import/export project registry
- Git integration
- Local web dashboard
- Automatic backup before cleanup
- Usage analytics and trends

### Advanced Capabilities
- Detect project dependencies
- Track build times
- Monitor compilation errors
- CI/CD integration
- Team-shared project registries
- Cloud backup support

## Success Metrics

### Space Savings
- Typical project cleanup target: 2 GB to 50 MB (97.5% reduction)
- Example portfolio cleanup: 20 old projects can free roughly 39 GB

### Time Savings
- Less manual version switching
- No manual project inventory tracking
- Faster cleanup decisions
- Faster project discovery

## Platform Support

### Primary: Windows
- Full feature support target
- Native executable
- PATH integration
- Visual Studio integration

### Secondary: Linux
- Full feature support target
- Shell integration
- Generator compatibility

## Installation

### Quick Install (PowerShell)
```powershell
irm https://cmakectl.dev/install.ps1 | iex
```

### Manual Install
```bash
git clone https://github.com/user/cmakectl
cd cmakectl
python -m pip install -e .
# Copy cmake.exe to PATH
```

### Setup Wizard Example
```text
Welcome to CMake Control!

This tool will:
- Manage multiple CMake versions
- Track all your CMake projects automatically
- Help you clean up old build artifacts

Setup:
[1/4] Choose installation directory: C:\Tools\cmakectl
[2/4] Scan for existing CMake installations? [Y/n]
[3/4] Scan for existing projects? [Y/n]
[4/4] Add to PATH? [Y/n]

Setup complete.

Try: cmakectl install 3.28.1
```

## Design Principles
- Zero friction: no workflow changes required
- Transparency: minimal user overhead
- Performance: fast enough to be invisible
- Safety: no destructive operations without explicit approval or policy
- Flexibility: works with any CMake project
- Maintainability: clear separation of concerns
- Extensibility: feature growth without redesign

## Version Switching UX Rules
- Default `cmakectl use <version> --project <path>` is persistent for that project.
- Optional `--session` applies only to the current shell session and does not change persistent project mapping.
- If a project has no identity metadata and requested version differs from global, tool can prompt:
  - Save for this project (persistent)
  - Apply only for this session
  - Keep global version
- Global version changes apply to already-open terminals on next `cmake` command because resolution occurs per invocation in proxy.
- Running commands are never interrupted or mutated mid-execution.

## Related Documents
- V1 architecture checklist and acceptance criteria: see docs/V1-CHECKLIST.md
