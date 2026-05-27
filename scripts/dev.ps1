$ErrorActionPreference = "Stop"

python -m pip install -r requirements.txt
Push-Location approval-web
npm install
Pop-Location
python -m bugfix_automation.cli init
python -m bugfix_automation.cli approval-server
