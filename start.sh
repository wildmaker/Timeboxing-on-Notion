#!/bin/bash

# Notion自动化工具 - 一键启动脚本
# 适用于 macOS/Linux 系统

set -e  # 遇到错误时立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的信息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

print_info "🚀 启动 Notion 自动化工具..."
print_info "📁 项目目录: $PROJECT_DIR"

# 切换到项目目录
cd "$PROJECT_DIR"

# 检查虚拟环境
VENV_DIR="$PROJECT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
    print_warning "⚠️  虚拟环境不存在，正在创建..."
    python3 -m venv venv
    print_success "✅ 虚拟环境创建成功"
else
    print_info "✅ 虚拟环境已存在"
fi

# 激活虚拟环境
print_info "🔧 激活虚拟环境..."
source "$VENV_DIR/bin/activate"

# 检查并安装依赖
print_info "📦 检查并安装依赖..."
if [ -f "requirements.txt" ]; then
    print_info "正在安装依赖包..."
    pip install -r requirements.txt
    print_success "✅ 依赖包安装完成"
else
    print_warning "⚠️  requirements.txt 文件不存在"
fi

# 检查必要的配置文件
if [ ! -f ".env" ]; then
    print_warning "⚠️  .env 文件不存在，请确保已配置环境变量"
fi

# 检查数据库迁移
print_info "🗄️  检查数据库状态..."
if [ -d "migrations" ]; then
    print_info "正在执行数据库迁移..."
    python -m flask db upgrade
    print_success "✅ 数据库迁移完成"
fi

# 启动应用
print_info "🌟 启动应用..."
print_success "✅ 应用正在启动，请访问: http://localhost:5001"
print_info "按 Ctrl+C 停止应用"

# 启动Flask应用
python run.py 