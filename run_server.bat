@echo off
title VitalRoute Core Server - FastAPI
echo ======================================================================
echo           VITALROUTE REGIONAL EMERGENCY DISPATCH CORE
echo ======================================================================
echo Starting server on http://localhost:8000 ...
echo Mobile Paramedic App: http://localhost:8000/mobile
echo Main Dispatch HUD:    http://localhost:8000/
echo Interactive API Docs: http://localhost:8000/docs
echo ======================================================================
cd /d "%~dp0backend"
python run.py
pause
