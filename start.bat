@echo off
REM Notion自动化工具 - 一键启动脚本
REM 适用于 Windows 系统

chcp 65001 > nul
setlocal enabledelayedexpansion

REM 获取脚本所在目录
set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%"

echo.
echo 🚀 启动 Notion 自动化工具...
echo 📁 项目目录: %PROJECT_DIR%
echo.

REM 切换到项目目录
cd /d "%PROJECT_DIR%"

REM 检查虚拟环境
set "VENV_DIR=%PROJECT_DIR%venv"
if not exist "%VENV_DIR%" (
    echo ⚠️  虚拟环境不存在，正在创建...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo ❌ 虚拟环境创建失败，请检查Python是否正确安装
        pause
        exit /b 1
    )
    echo ✅ 虚拟环境创建成功
) else (
    echo ✅ 虚拟环境已存在
)

REM 激活虚拟环境
echo.
echo 🔧 激活虚拟环境...
call "%VENV_DIR%\Scripts\activate.bat"

REM 检查并安装依赖
echo.
echo 📦 检查并安装依赖...
if exist "requirements.txt" (
    echo 正在安装依赖包...
    pip install -r requirements.txt
    if !errorlevel! neq 0 (
        echo ❌ 依赖包安装失败
        pause
        exit /b 1
    )
    echo ✅ 依赖包安装完成
) else (
    echo ⚠️  requirements.txt 文件不存在
)

REM 检查必要的配置文件
if not exist ".env" (
    echo ⚠️  .env 文件不存在，请确保已配置环境变量
)

REM 检查数据库迁移
echo.
echo 🗄️  检查数据库状态...
if exist "migrations" (
    echo 正在执行数据库迁移...
    python -m flask db upgrade
    if !errorlevel! neq 0 (
        echo ⚠️  数据库迁移可能失败，但继续启动应用
    ) else (
        echo ✅ 数据库迁移完成
    )
)

REM 启动应用
echo.
echo 🌟 启动应用...
echo ✅ 应用正在启动，请访问: http://localhost:5001
echo 按 Ctrl+C 停止应用
echo.

REM 启动Flask应用
python run.py

pause 