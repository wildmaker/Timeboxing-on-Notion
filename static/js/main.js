/**
 * Notion 自动化工具 - 主要 JavaScript 文件
 */

document.addEventListener('DOMContentLoaded', function() {
    // 自动关闭警告消息
    setupAlertDismiss();
    
    // 设置表单验证
    setupFormValidation();
});

/**
 * 设置警告消息自动关闭
 */
function setupAlertDismiss() {
    const alerts = document.querySelectorAll('.alert:not(.alert-dismissible)');
    
    alerts.forEach(alert => {
        if (alert.classList.contains('alert-success')) {
            // 成功消息 3 秒后自动关闭
            setTimeout(() => {
                fadeOut(alert);
            }, 3000);
        }
    });
}

/**
 * 设置表单验证
 */
function setupFormValidation() {
    const forms = document.querySelectorAll('form');
    
    forms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
                
                // 高亮显示未填写的必填字段
                const requiredFields = form.querySelectorAll('[required]');
                requiredFields.forEach(field => {
                    if (!field.value) {
                        field.classList.add('is-invalid');
                        
                        // 字段获得焦点后移除错误样式
                        field.addEventListener('focus', function() {
                            this.classList.remove('is-invalid');
                        }, { once: true });
                    }
                });
            }
        });
    });
}

/**
 * 元素淡出效果
 * @param {HTMLElement} element - 要淡出的元素
 * @param {number} duration - 淡出持续时间（毫秒）
 */
function fadeOut(element, duration = 500) {
    element.style.transition = `opacity ${duration}ms ease-out`;
    element.style.opacity = '0';
    
    setTimeout(() => {
        element.style.display = 'none';
        element.style.height = '0';
        element.style.margin = '0';
        element.style.padding = '0';
    }, duration);
}

/**
 * 处理选择数据库的逻辑
 * @param {string} databaseId - 数据库 ID
 * @param {string} databaseUrl - 数据库 URL
 */
function selectDatabase(databaseId, databaseUrl) {
    if (document.getElementById('database_url')) {
        document.getElementById('database_url').value = databaseUrl;
    }
    
    if (document.getElementById('database_id')) {
        const selectElement = document.getElementById('database_id');
        
        // 遍历选项，找到匹配的数据库 ID
        for (let i = 0; i < selectElement.options.length; i++) {
            if (selectElement.options[i].value === databaseId) {
                selectElement.selectedIndex = i;
                break;
            }
        }
    }
}

/**
 * 格式化日期时间
 * @param {Date} date - 日期对象
 * @returns {string} 格式化后的日期时间字符串
 */
function formatDateTime(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    
    return `${year}-${month}-${day} ${hours}:${minutes}`;
}

/**
 * 计算延迟后的日期
 * @param {number} hours - 延迟小时数
 * @param {number} minutes - 延迟分钟数
 * @returns {string} 延迟后的日期时间字符串
 */
function calculateDelayedDateTime(hours, minutes) {
    const now = new Date();
    const delayed = new Date(now.getTime() + (hours * 60 * 60 * 1000) + (minutes * 60 * 1000));
    
    return formatDateTime(delayed);
}
