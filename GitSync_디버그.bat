@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo ==============================================
echo  깃싱크 (GitSync) - 실행 콘솔
echo ==============================================
python app.py
pause
