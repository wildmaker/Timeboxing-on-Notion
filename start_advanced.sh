#!/bin/bash

# Notion自动化工具 - 智能启动脚本
# 适用于 macOS/Linux 系统
# 包含端口检查、依赖优化、日志记录等高级功能

set -e  # 遇到错误时立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 配置
APP_NAME="Notion自动化工具"
APP_PORT=5001
LOG_DIR="logs"
REQUIREMENTS_FILE="requirements.txt"
VENV_NAME="venv"

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

print_debug() {
    echo -e "${PURPLE}[DEBUG]${NC} $1"
}

print_header() {
    echo -e "${CYAN}========================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}========================================${NC}"
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 检查端口是否被占用
check_port() {
    if command_exists lsof; then
        if lsof -i :$APP_PORT >/dev/null 2>&1; then
            print_warning "⚠️  端口 $APP_PORT 已被占用"
            print_info "正在查找占用端口的进程..."
            lsof -i :$APP_PORT
            read -p "是否要终止占用端口的进程？(y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                print_info "终止占用端口的进程..."
                lsof -ti :$APP_PORT | xargs kill -9
                print_success "✅ 已终止占用端口的进程"
            else
                print_error "❌ 无法启动应用，端口被占用"
                exit 1
            fi
        fi
    fi
}

# 检查Python版本
check_python() {
    if command_exists python3; then
        PYTHON_CMD="python3"
    elif command_exists python; then
        PYTHON_CMD="python"
    else
        print_error "❌ 未找到Python，请先安装Python"
        exit 1
    fi
    
    python_version=$($PYTHON_CMD --version 2>&1)
    print_info "🐍 Python版本: $python_version"
    
    # 检查Python版本是否符合要求（建议3.7+）
    if $PYTHON_CMD -c "import sys; exit(0 if sys.version_info >= (3, 7) else 1)"; then
        print_success "✅ Python版本符合要求"
    else
        print_warning "⚠️  建议使用Python 3.7或更高版本"
    fi
}

# 创建日志目录
create_log_dir() {
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR"
        print_info "📁 创建日志目录: $LOG_DIR"
    fi
}

# 检查虚拟环境并创建
setup_venv() {
    if [ ! -d "$VENV_NAME" ]; then
        print_warning "⚠️  虚拟环境不存在，正在创建..."
        $PYTHON_CMD -m venv "$VENV_NAME"
        print_success "✅ 虚拟环境创建成功"
    else
        print_info "✅ 虚拟环境已存在"
    fi
    
    # 激活虚拟环境
    print_info "🔧 激活虚拟环境..."
    source "$VENV_NAME/bin/activate"
    
    # 更新pip
    print_info "📦 更新pip..."
    pip install --upgrade pip >/dev/null 2>&1
}

# 智能依赖安装
install_dependencies() {
    if [ -f "$REQUIREMENTS_FILE" ]; then
        print_info "📦 检查依赖包..."
        
        # 检查是否需要安装依赖
        if [ -f "$VENV_NAME/pyvenv.cfg" ]; then
            # 检查requirements.txt是否比安装的包新
            if [ "$REQUIREMENTS_FILE" -nt "$VENV_NAME/lib" ] || [ ! -f "$VENV_NAME/.dependencies_installed" ]; then
                print_info "正在安装/更新依赖包..."
                pip install -r "$REQUIREMENTS_FILE"
                touch "$VENV_NAME/.dependencies_installed"
                print_success "✅ 依赖包安装完成"
            else
                print_success "✅ 依赖包已是最新版本"
            fi
        else
            print_info "首次安装依赖包..."
            pip install -r "$REQUIREMENTS_FILE"
            touch "$VENV_NAME/.dependencies_installed"
            print_success "✅ 依赖包安装完成"
        fi
    else
        print_warning "⚠️  $REQUIREMENTS_FILE 文件不存在"
    fi
}

# 检查环境配置
check_environment() {
    if [ ! -f ".env" ]; then
        print_warning "⚠️  .env 文件不存在"
        print_info "创建示例.env文件..."
        cat > .env << EOF
# Notion API配置
NOTION_API_TOKEN=your_notion_api_token_here

# 数据库配置
DATABASE_URL=sqlite:///instance/app.db

# Flask配置
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your_secret_key_here
EOF
        print_success "✅ 已创建示例.env文件，请配置你的API密钥"
    fi
}

# 数据库迁移
handle_database() {
    if [ -d "migrations" ]; then
        print_info "🗄️  检查数据库状态..."
        
        # 检查是否需要迁移
        if $PYTHON_CMD -c "
import sys
sys.path.append('.')
try:
    from flask_migrate import current
    from app import create_app
    app = create_app()
    with app.app_context():
        current()
    print('Database is up to date')
except Exception as e:
    print(f'Database migration needed: {e}')
    sys.exit(1)
" 2>/dev/null; then
            print_success "✅ 数据库已是最新版本"
        else
            print_info "正在执行数据库迁移..."
            $PYTHON_CMD -m flask db upgrade
            print_success "✅ 数据库迁移完成"
        fi
    else
        print_info "🗄️  初始化数据库..."
        $PYTHON_CMD -c "
import sys
sys.path.append('.')
from app import create_app
from models.database import db
app = create_app()
with app.app_context():
    db.create_all()
print('Database initialized')
"
        print_success "✅ 数据库初始化完成"
    fi
}

# 启动应用
start_application() {
    print_info "🌟 启动应用..."
    print_success "✅ 应用正在启动，请访问: http://localhost:$APP_PORT"
    print_info "📝 日志文件位置: $LOG_DIR/"
    print_info "⏹️  按 Ctrl+C 停止应用"
    echo
    
    # 创建启动日志
    TIMESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')
    LOG_FILE="$LOG_DIR/app_${TIMESTAMP}.log"
    
    # 启动应用并记录日志
    $PYTHON_CMD run.py 2>&1 | tee "$LOG_FILE"
}

# 清理函数
cleanup() {
    print_info "🧹 正在清理..."
    # 这里可以添加清理逻辑
    print_success "✅ 清理完成"
}

# 信号处理
trap cleanup EXIT

# 主程序
main() {
    print_header "$APP_NAME - 智能启动脚本"
    
    # 获取脚本所在目录
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_DIR="$SCRIPT_DIR"
    
    print_info "📁 项目目录: $PROJECT_DIR"
    
    # 切换到项目目录
    cd "$PROJECT_DIR"
    
    # 执行启动流程
    print_header "环境检查"
    check_python
    check_port
    
    print_header "环境准备"
    create_log_dir
    setup_venv
    install_dependencies
    check_environment
    
    print_header "数据库准备"
    handle_database
    
    print_header "启动应用"
    start_application
}

# 运行主程序
main "$@" 