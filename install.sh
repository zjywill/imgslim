#!/bin/bash
# imgslim installer — links the skill into Claude Code and Codex, installs codec deps.
set -euo pipefail
cd "$(dirname "$0")"
SKILL_SRC="$PWD/skills/imgslim"

echo "== codec dependencies =="
if command -v brew >/dev/null; then
  MISSING=()
  command -v pngquant >/dev/null || MISSING+=(pngquant)
  command -v oxipng   >/dev/null || MISSING+=(oxipng)
  command -v cwebp    >/dev/null || MISSING+=(webp)
  command -v dssim    >/dev/null || MISSING+=(dssim)
  [ -x "$(brew --prefix)/opt/mozjpeg/bin/cjpeg" ] 2>/dev/null || MISSING+=(mozjpeg)
  if [ ${#MISSING[@]} -gt 0 ]; then
    echo "installing: ${MISSING[*]}"
    brew install "${MISSING[@]}"
  else
    echo "all present"
  fi
elif command -v apt-get >/dev/null; then
  echo "Linux: sudo apt install pngquant webp imagemagick; cargo install oxipng dssim"
  echo "mozjpeg: build from github.com/mozilla/mozjpeg (or use libjpeg-turbo's cjpeg)"
else
  echo "Windows: scoop install pngquant libwebp mozjpeg imagemagick"
  echo "dssim/oxipng: grab releases from github.com/kornelski/dssim and shssoichiro/oxipng"
fi

echo "== Claude Code =="
mkdir -p "$HOME/.claude/skills"
ln -sfn "$SKILL_SRC" "$HOME/.claude/skills/imgslim"
echo "linked ~/.claude/skills/imgslim"
echo "(alternatively, as a plugin: /plugin marketplace add zjywill/imgslim)"

echo "== Codex =="
mkdir -p "$HOME/.codex/skills"
ln -sfn "$SKILL_SRC" "$HOME/.codex/skills/imgslim"
echo "linked ~/.codex/skills/imgslim"

echo
echo "verify: python3 '$SKILL_SRC/scripts/imgslim.py' deps"
