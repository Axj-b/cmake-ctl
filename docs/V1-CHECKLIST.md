# CMake Control Center - V1 Checklist and Acceptance Criteria

## Revised V1 Architecture Checklist

### 1) Proxy Execution Safety (Must)
- [ ] Proxy resolves target CMake executable by absolute path from managed versions, not PATH lookup.
- [ ] Proxy detects self-recursion (resolved target equals current executable path) and fails fast with a clear error.
- [ ] Proxy passes all arguments unchanged and returns exact child process exit code.
- [ ] Proxy sets a lightweight recursion-guard environment variable for nested invocations.

### 2) Version Resolution Rules (Must)
- [ ] Resolution order is deterministic and documented:
  1. Explicit CLI override (if provided)
  2. Session override (`cmakectl use <ver> --session`)
  3. Project-persistent mapping
  4. Project .cmake-version near source directory
  5. Global default in config
  6. Latest installed version
- [ ] Source directory discovery supports -S/-B, configure presets, and invocation from a build directory.
- [ ] If no managed version is available, command fails with actionable remediation text.
- [ ] Session override is scoped to current shell session and never mutates persistent project mapping unless explicitly requested.

### 2b) Project Identity and Move Handling (Must)
- [ ] Identity strategy is configurable: `id-file-first` or `path-only`.
- [ ] In `id-file-first` mode, `.cmakectl/project-id` is used as stable identity and canonical path is fallback.
- [ ] If project-id matches but path changes, mapping is reconciled to new canonical path safely.
- [ ] If no project-id is available, path fallback behavior is deterministic and documented.

### 3) Event Queue Reliability (Must)
- [ ] Event records use newline-delimited JSON with schema version.
- [ ] Writes are append-only and atomic per record.
- [ ] Queue processing is idempotent using event_id deduplication.
- [ ] Corrupt lines are quarantined to a dead-letter file and do not block processing.
- [ ] Queue supports rotation/compaction policy to prevent unbounded growth.

### 4) Database Concurrency (Must)
- [ ] SQLite uses WAL mode.
- [ ] One-writer process pattern (or serialized writes) is enforced.
- [ ] Retries with backoff on SQLITE_BUSY are implemented.
- [ ] Schema migrations are versioned and reversible.

### 5) Cleanup Safety Model (Must)
- [ ] Deletion targets are constrained to known build outputs discovered from CMake metadata where possible.
- [ ] Path safety checks block deletes outside approved project/build roots.
- [ ] Dry-run output includes exact files/dirs and total reclaimable bytes.
- [ ] Pinned projects are never auto-cleaned.
- [ ] Optional archive-before-delete mode stores a manifest and timestamp.

### 6) Download and Binary Integrity (Must)
- [ ] Download manifest includes expected SHA256 for each artifact.
- [ ] Installer verifies checksum before extraction and activation.
- [ ] Failed verification leaves no partially active installation.
- [ ] Network and checksum failures provide clear diagnostics.

### 7) Cross-Platform Contract (Should)
- [ ] Windows and Linux behavior is equivalent for version resolution and tracking.
- [ ] Platform-specific install steps are documented separately.
- [ ] Integration behavior is validated for common generators (Visual Studio, Ninja, Unix Makefiles).

### 8) Observability and UX (Should)
- [ ] Verbose mode logs resolution decisions and chosen CMake path.
- [ ] User-facing errors are concise and include a next action.
- [ ] stats/analyze commands handle missing or partial data gracefully.

### 9) TUI Experience (Should)
- [ ] `cmakectl tui` launches a guided terminal UI for core actions (install, use, projects, clean, stats).
- [ ] TUI displays active source of version resolution (session, project, file, global).
- [ ] TUI uses safe defaults for destructive actions (preview + confirmation).

### 10) Global Switch Propagation in Open Terminals (Must)
- [ ] Changing global version requires no terminal restart.
- [ ] Already-open terminals use the new global version on next `cmake` invocation.
- [ ] Running commands are never mutated mid-execution.

## V1 Acceptance Criteria

### A. End-to-End Routing
- Given three installed versions, running cmake in three projects with different .cmake-version values launches the expected binary every time.
- Exit codes and stdout/stderr are preserved exactly relative to direct CMake execution.
- Median proxy overhead is <= 10 ms on Windows for warm runs.
- Given a session override, resolver selects session version over project/file/global for that session only.

### B. Concurrency and Queue Robustness
- 100 concurrent configure invocations produce 100 processable events without loss.
- Re-processing the same queue file does not duplicate project updates.
- Injected malformed events are isolated and reported while valid events continue processing.

### C. Cleanup Safety
- Dry-run and real-run produce consistent target sets.
- Safety checks prevent deletion outside project/build roots.
- Pinned projects are skipped in all bulk cleanup operations.

### D. Integrity and Installation
- Tampered download fails checksum validation and is never activated.
- Successful install writes version metadata and executable path atomically.

### E. Database and Recovery
- Under active event ingestion and size scans, no user-visible command fails due to persistent DB locking.
- Restart after abrupt termination resumes queue processing without data corruption.

### F. Cross-Platform Baseline
- Core commands (install, list, use, projects, clean --dry-run, stats) pass smoke tests on Windows and Linux.
- `cmakectl tui` launches and performs basic navigation on Windows and Linux terminals.

### G. Open Terminal Global Switch
- After `cmakectl use <ver>` sets global default, already-open terminals select new global version on the next `cmake` run without restart.
- In-flight cmake executions are unaffected.

### H. Project Move Behavior
- In `id-file-first` mode, moving a project directory preserves version mapping via `.cmakectl/project-id`.
- In `path-only` mode, moved directories are treated as new project paths.

## Suggested V1 Test Matrix

### Functional
- Version selection from source dir, build dir, and preset-based invocation.
- Project registration updates configureCount, lastConfigured, and generator correctly.
- Session vs persistent precedence (`--session` vs project mapping vs global).
- Project move tests for `id-file-first` and `path-only` modes.
- TUI smoke flow: open, select version, inspect active source, exit cleanly.

### Resilience
- Simulated power loss during queue write and during DB write.
- Locked-file and permission-denied scenarios for cleanup.

### Performance
- Proxy startup overhead benchmark.
- Queue processing throughput with large backlogs.

### Security
- Checksum verification path, tampered artifact test, and rollback behavior.
