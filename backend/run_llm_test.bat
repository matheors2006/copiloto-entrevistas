@echo off
chcp 65001 >nul
title LLM Engine Test
cd /d "%~dp0"
venv\Scripts\python.exe -u llm_engine.py
echo.
echo (Presiona una tecla para cerrar esta ventana)
pause >nul
