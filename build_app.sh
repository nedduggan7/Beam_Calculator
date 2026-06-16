#!/usr/bin/env bash
set -euo pipefail

export PYINSTALLER_CONFIG_DIR="$PWD/.pyinstaller"

python3 -m PyInstaller \
  --name "Beam Calculator" \
  --windowed \
  --clean \
  --noconfirm \
  app.py

ditto -c -k --keepParent "dist/Beam Calculator.app" "dist/Beam Calculator-macOS.zip"
hdiutil create \
  -volname "Beam Calculator" \
  -srcfolder "dist/Beam Calculator.app" \
  -ov \
  -format UDZO \
  "dist/Beam Calculator-macOS.dmg"
