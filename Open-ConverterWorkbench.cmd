@echo off
setlocal
set "app=%~dp0build\ConverterWorkbench\EU5Converter.exe"
if exist "%app%" (
  start "" "%app%"
) else (
  echo Please build the workbench with tools\Build-ConverterApp.ps1 first.
  pause
)
