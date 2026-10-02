@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Start-LocationWorkstation.ps1"
if errorlevel 1 pause
