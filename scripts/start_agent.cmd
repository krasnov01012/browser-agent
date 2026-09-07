@echo off
rem Double-clickable wrapper. ASCII only: .cmd is read in the OEM codepage,
rem Cyrillic here would arrive as garbage. All messages live in the .ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_agent.ps1" %*
pause
