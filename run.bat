@echo off
REM Runs the P2P network with the given config (defaults to config.yaml).
set CONFIG=%1
if "%CONFIG%"=="" set CONFIG=config.yaml
.\.venv\Scripts\python.exe -m p2p %CONFIG%
