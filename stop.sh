#!/bin/bash

# Notion自动化工具 - 停止脚本
# 适用于 macOS/Linux 系统

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
APP_PORT=5001
APP_NAME="Notion自动化工具"

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

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 停止应用
stop_application() {
    print_info "🛑 正在停止 $APP_NAME..."
    
    if command_exists lsof; then
        # 查找占用端口的进程
        PIDS=$(lsof -ti :$APP_PORT 2>/dev/null || true)
        
        if [ -n "$PIDS" ]; then
            print_info "发现运行中的应用进程: $PIDS"
            
            # 尝试优雅关闭
            print_info "尝试优雅关闭应用..."
            echo "$PIDS" | xargs kill -TERM 2>/dev/null || true
            
            # 等待2秒
            sleep 2
            
            # 检查是否还在运行
            REMAINING_PIDS=$(lsof -ti :$APP_PORT 2>/dev/null || true)
            if [ -n "$REMAINING_PIDS" ]; then
                print_warning "应用仍在运行，强制终止..."
                echo "$REMAINING_PIDS" | xargs kill -KILL 2>/dev/null || true
                sleep 1
            fi
            
            # 最终检查
            FINAL_PIDS=$(lsof -ti :$APP_PORT 2>/dev/null || true)
            if [ -z "$FINAL_PIDS" ]; then
                print_success "✅ 应用已成功停止"
            else
                print_error "❌ 无法停止应用，进程仍在运行"
                exit 1
            fi
        else
            print_warning "⚠️  没有发现运行中的应用"
        fi
    else
        print_error "❌ 无法使用lsof命令，请手动停止应用"
        exit 1
    fi
}

# 清理临时文件
cleanup_temp_files() {
    print_info "🧹 清理临时文件..."
    
    # 清理Python缓存
    if [ -d "__pycache__" ]; then
        rm -rf __pycache__
        print_info "已清理Python缓存"
    fi
    
    # 清理.pyc文件
    find . -name "*.pyc" -delete 2>/dev/null || true
    
    # 清理Flask实例文件夹中的临时文件
    if [ -d "instance" ]; then
        find instance -name "*.tmp" -delete 2>/dev/null || true
    fi
    
    print_success "✅ 临时文件清理完成"
}

# 主程序
main() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  $APP_NAME - 停止脚本${NC}"
    echo -e "${BLUE}========================================${NC}"
    
    stop_application
    cleanup_temp_files
    
    print_success "🎉 停止操作完成"
}

# 运行主程序
main "$@" 