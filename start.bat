@echo off
cd /d "%~dp0"
echo Starting AquaState at http://127.0.0.1:8010/
start "AquaState refresher" cmd /k python manage.py refresh_world --loop --interval 900
python manage.py runserver 127.0.0.1:8010
