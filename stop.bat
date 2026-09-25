@echo off
rem Stops the Veyro server window.
taskkill /FI "WINDOWTITLE eq Veyro server*" /T /F >nul 2>nul
echo Veyro stopped.
ping -n 3 127.0.0.1 >nul
