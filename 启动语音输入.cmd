@echo off
rem 实时语音输入小助手启动脚本：进入本目录并用当前 Python 环境运行主程序
cd /d "%~dp0"
start "" /b pythonw main.py
if errorlevel 1 (
  echo.
  echo start failed. See the error above.
  pause
)
