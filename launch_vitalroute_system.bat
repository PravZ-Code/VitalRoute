@echo off
title VitalRoute Flagship Emergency Coordination System
echo ======================================================================
echo           VITALROUTE FLAGSHIP EMERGENCY COORDINATION SYSTEM
echo           (Tauri 2 + React + Python Decision Core)
echo ======================================================================
echo.
echo [1/2] Starting VitalRoute Decision Core Sidecar (Port 8000)...
start /b "" "%~dp0vitalroute-core.exe"
timeout /t 2 /nobreak >nul

echo [2/2] Launching VitalRoute Hospital Triage HUD Desktop Application...
start "" "%~dp0VitalRoute_Hospital_Triage.exe"

echo.
echo ======================================================================
echo System active!
echo - Hospital HUD: Running natively via Tauri 2 + React
echo - Mobile Paramedic App: http://localhost:8000/mobile
echo ======================================================================
