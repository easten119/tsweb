@echo off
rem TAESUNG WEB launcher - closing this window stops the app
chcp 65001 > nul
cd /d "%~dp0"
title TAESUNG WEB
set "PY=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" run.py