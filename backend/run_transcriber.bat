@echo off
chcp 65001 >nul
title Deepgram Transcriber
cd /d "%~dp0"
venv\Scripts\python.exe -u transcriber.py
pause