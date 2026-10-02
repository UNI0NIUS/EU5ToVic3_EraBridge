@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Start-TerrainWorkstation.ps1"
if errorlevel 1 pause
