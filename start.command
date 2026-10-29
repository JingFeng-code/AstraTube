#!/usr/bin/env bash
# macOS: double-click this file in Finder to start Youtube Card Reader.
cd "$(dirname "$0")"
chmod +x scripts/start.sh 2>/dev/null
./scripts/start.sh
echo
read -r -p "Press Enter to close this window…" _
