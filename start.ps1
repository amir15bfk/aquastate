$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "Starting AquaState at http://127.0.0.1:8010/"
Write-Host "A second window will run the 15-minute world refresh loop."

Start-Process powershell -WindowStyle Minimized -ArgumentList @(
  "-NoExit",
  "-Command",
  "Set-Location '$root'; python manage.py refresh_world --loop --interval 900"
)

python manage.py runserver 127.0.0.1:8010
