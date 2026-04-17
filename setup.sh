#!/usr/bin/env bash
# cmake-ctl setup script for Linux/macOS.
# Adds the bin folder to PATH (via shell profile) and optionally configures VSCode.
#
# Usage:
#   ./setup.sh
#   ./setup.sh --vscode
#   ./setup.sh --uninstall

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$SCRIPT_DIR/bin"
PROXY_EXE="$BIN_DIR/cmake"

ok()   { printf "  \033[32m[OK]\033[0m %s\n" "$*"; }
info() { printf "  \033[36m[..]\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m[!!]\033[0m %s\n" "$*"; }
fail() { printf "  \033[31m[XX]\033[0m %s\n" "$*"; exit 1; }

VSCODE_FLAG=0
UNINSTALL_FLAG=0
for arg in "$@"; do
  case "$arg" in
    --vscode)    VSCODE_FLAG=1 ;;
    --uninstall) UNINSTALL_FLAG=1 ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

# Detect shell profile
detect_profile() {
  if [ -n "${BASH_VERSION:-}" ]; then
    echo "${HOME}/.bashrc"
  elif [ -n "${ZSH_VERSION:-}" ]; then
    echo "${HOME}/.zshrc"
  elif [ -f "${HOME}/.profile" ]; then
    echo "${HOME}/.profile"
  else
    echo "${HOME}/.profile"
  fi
}

PROFILE="$(detect_profile)"
EXPORT_LINE="export PATH=\"$BIN_DIR:\$PATH\" # cmake-ctl"

get_vscode_settings() {
  # Linux/macOS standard locations
  local candidates=(
    "$HOME/.config/Code/User/settings.json"
    "$HOME/.config/Code - Insiders/User/settings.json"
    "$HOME/Library/Application Support/Code/User/settings.json"
  )
  for p in "${candidates[@]}"; do
    [ -f "$p" ] && echo "$p" && return
  done
  echo "${candidates[0]}"
}

update_vscode_settings() {
  local settings_path="$1"
  local remove="${2:-0}"
  local proxy_path
  proxy_path="$(echo "$PROXY_EXE" | sed 's/\\/\//g')"

  if [ ! -f "$settings_path" ]; then
    [ "$remove" = "1" ] && { warn "VSCode settings not found – nothing to remove."; return; }
    mkdir -p "$(dirname "$settings_path")"
    echo "{}" > "$settings_path"
  fi

  if command -v python3 &>/dev/null; then
    python3 - "$settings_path" "$proxy_path" "$remove" <<'PYEOF'
import json, sys

path, proxy, remove = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
with open(path, "r", encoding="utf-8") as f:
    settings = json.load(f)

if remove:
    settings.pop("cmake.cmakePath", None)
else:
    settings["cmake.cmakePath"] = proxy

with open(path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=4)
PYEOF
    if [ "$remove" = "1" ]; then
      ok "Removed cmake.cmakePath from $settings_path"
    else
      ok "Set cmake.cmakePath = $proxy_path in $settings_path"
    fi
  else
    warn "python3 not found – skipping VSCode settings update."
  fi
}

printf "\n\033[34mcmake-ctl setup\033[0m\n"
printf "%-50s\n" "──────────────────────────────────────────────────"
info "Bin directory : $BIN_DIR"
info "Proxy exe     : $PROXY_EXE"
info "Shell profile : $PROFILE"
printf "\n"

if [ "$UNINSTALL_FLAG" = "1" ]; then
  info "Uninstalling cmake-ctl..."
  # Remove PATH line from profile
  if grep -qF "$EXPORT_LINE" "$PROFILE" 2>/dev/null; then
    grep -vF "$EXPORT_LINE" "$PROFILE" > "$PROFILE.tmp" && mv "$PROFILE.tmp" "$PROFILE"
    ok "Removed cmake-ctl from $PROFILE"
  else
    warn "cmake-ctl not found in $PROFILE – nothing to remove."
  fi
  VSC_SETTINGS="$(get_vscode_settings)"
  update_vscode_settings "$VSC_SETTINGS" "1"
  printf "\n"
  ok "Uninstall complete."
  exit 0
fi

# Validate proxy exists
[ -f "$PROXY_EXE" ] || fail "Proxy not found at $PROXY_EXE. Run build.sh first."

# Add to PATH in profile
if grep -qF "# cmake-ctl" "$PROFILE" 2>/dev/null; then
  warn "$BIN_DIR is already in $PROFILE – skipping."
else
  printf "\n%s\n" "$EXPORT_LINE" >> "$PROFILE"
  ok "Added $BIN_DIR to PATH in $PROFILE"
  warn "Run: source $PROFILE  (or open a new terminal)"
fi

# Also export into the current shell session
export PATH="$BIN_DIR:$PATH"

# VSCode settings
if [ "$VSCODE_FLAG" = "1" ]; then
  VSC_SETTINGS="$(get_vscode_settings)"
  info "VSCode settings: $VSC_SETTINGS"
  update_vscode_settings "$VSC_SETTINGS" "0"
else
  warn "Skipping VSCode setup (pass --vscode to enable)."
fi

printf "\n"
ok "Setup complete. You can now use 'cmake' and 'cmake-ctl' from any terminal."
printf "\n"
