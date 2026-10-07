#!/bin/zsh
cd "${0:A:h}"
if ! command -v node >/dev/null; then
  echo 'Install Node.js 20+ first. See GETTING_STARTED.md.'
  read '?Press Enter to close.'
  exit 1
fi
node scripts/start.mjs --open
if [[ $? -ne 0 ]]; then read '?Startup failed. Read the message above; press Enter to close.'; fi
