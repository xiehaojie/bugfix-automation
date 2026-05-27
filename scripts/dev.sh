#!/usr/bin/env bash
set -euo pipefail

python3 -m pip install -r requirements.txt
(cd approval-web && npm install)
python3 -m bugfix_automation.cli init
python3 -m bugfix_automation.cli approval-server
