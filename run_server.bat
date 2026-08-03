@echo off
title Document Validator Server
echo.
echo  ============================================
echo   Document Validator Bridge Server v1.0
echo  ============================================
echo.
echo  Starting server on http://localhost:8765
echo  Keep this window open while using the extension.
echo  Press Ctrl+C to stop.
echo.
python server.py
pause
