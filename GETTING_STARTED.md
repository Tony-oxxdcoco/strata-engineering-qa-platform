# Getting started

[中文](docs/GETTING_STARTED.zh-CN.md) · [Project overview](README.md)

Install Python 3.12 and Node.js 20.11 or newer, then run `npm run setup` and `npm start` from this source directory. The first setup installs the declared open-source Python dependencies; there are no npm runtime packages or mandatory paid APIs. Open http://127.0.0.1:4180 and create your own account. Keep the service running while using the browser.

`npm run doctor` checks dependencies, write access and the port. `STRATA_PORT=4198 npm start` chooses another port in a macOS/Linux shell; in PowerShell use `$env:STRATA_PORT="4198"` before `npm start`. Windows can use the Setup/Start `.cmd` launchers; macOS can use the `.command` files. Automated test results do not by themselves verify every launcher/platform.

Accounts, project files and results persist in `.runtime/`. Do not delete or share it as source. Changing a password requires the current password; there is no password-recovery wizard. Keep credentials securely and never edit a password hash by hand. An isolated demo is preferable to modifying an existing data directory.

Create a project, choose Load example, approve the explicitly synthetic rule if needed, choose a supported check, inspect the result/evidence and export a record. A reviewer records human confirmation after reviewing current evidence and findings. `NOT VERIFIED` means required material/authority is unavailable, not a passed check.

See [Docker](docs/DOCKER.md), [adaptation](CLIENT_ADAPTATION.md), [verification](docs/frontend/VERIFICATION.md) and [contributing](CONTRIBUTING.md). Actual engineering inputs require independently approved rules and qualified review; included cases only verify software behavior.
