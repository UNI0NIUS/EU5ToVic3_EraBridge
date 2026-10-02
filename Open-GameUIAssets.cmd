@echo off
if not exist "%~dp0.local\game-ui-assets\index.html" (
  echo Run python tools\extract_game_ui_assets.py first.
  pause
  exit /b 1
)
start "" "%~dp0.local\game-ui-assets\index.html"
