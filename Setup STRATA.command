#!/bin/zsh
cd "${0:A:h}"
if ! command -v node >/dev/null; then
  echo 'Install Node.js 20+ from https://nodejs.org, then reopen Terminal.'
  read '?Press Enter to close.'
  exit 1
fi
node scripts/setup.mjs
if [[ $? -ne 0 ]]; then read '?Setup failed. Read the message above; press Enter to close.'; fi
