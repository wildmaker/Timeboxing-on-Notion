import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from config import Config
from models.database import db, CalendarDatabaseConfig, TaskOperation, ScheduleOperation
from notion_client import Client as NotionClient

from datetime import datetime, timedelta
import json
from sqlalchemy import inspect
from flask_migrate import Migrate
import pytz
from functools import wraps
from collections import defaultdict
from heapq import heappush, heappop
import math

# 辅助函数：根据优先级名称获取排序键
def get_priority_sort_key(priority_name):
    """将 'P0', 'P1', 'P2' 等优先级转换为可排序的数字"""
    if isinstance(priority_name, str) and priority_name.startswith('P'):
        try:
            return int(priority_name[1:])
        except (ValueError, IndexError):
            return 99  # 无效的 P 系列优先级，排在最后
    return 99 # 非 P 系列或无效的优先级，排在最后

def delete_today_rest_tasks(notion, config, mapping):
    """删除当天的所有休息任务"""
    try:
        # 获取当前日期范围（今天00:00到明天00:00）
        shanghai_tz = pytz.timezone('Asia/Shanghai')
        today_start = datetime.now(shanghai_tz).replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_start = today_start + timedelta(days=1)
        
        # 构建查询条件：包含"休息"关键词且在今天时间范围内的任务
        filter_conditions = {
            "and": [
                {
                    "property": mapping.get('title_property'),
                    "title": {
                        "contains": "🧘"  # 使用表情符号更精确匹配休息任务
                    }
                }
            ]
        }
        
        # 如果有时间属性，添加时间范围过滤
        timebox_start_property = mapping.get('timebox_start_property')
        if timebox_start_property:
            filter_conditions["and"].append({
                "property": timebox_start_property,
                "date": {
                    "on_or_after": today_start.isoformat(),
                    "before": tomorrow_start.isoformat()
                }
            })
        
        # 获取所有休息任务
        rest_tasks = notion.databases.query(
            database_id=config.database_id,
            filter=filter_conditions
        ).get('results', [])
        
        # 删除所有休息任务
        deleted_count = 0
        for task in rest_tasks:
            try:
                # 使用archive而不是delete，更安全
                notion.pages.update(
                    page_id=task['id'],
                    archived=True
                )
                deleted_count += 1
            except Exception as e:
                print(f"⚠️ 无法删除休息任务 {task['id']}: {str(e)}")
        
        print(f"🧘 成功删除 {deleted_count}/{len(rest_tasks)} 个休息任务")
        return deleted_count
        
    except Exception as e:
        print(f"❌ 删除休息任务时出错: {str(e)}")
        return 0

def get_pending_tasks(config, notion, mapping):
    """
    获取待排程的任务列表
    
    Args:
        config: 配置对象
        notion: NotionClient 实例
        mapping: 属性映射字典
    
    Returns:
        dict: 格式化的待排程任务字典 {task_id: task_data}
    """
    try:
        # 获取属性名称（不再需要转换为ID）
        timebox_start_property = mapping.get('timebox_start_property')
        schedule_status_property = mapping.get('schedule_status_property')
        schedule_status_todo_value = mapping.get('schedule_status_todo_value')
        schedule_status_done_value = mapping.get('schedule_status_done_value')
        parent_task_property = mapping.get('parent_task_property')
        priority_property = mapping.get('priority_property')

        shanghai_tz = pytz.timezone('Asia/Shanghai')
        today_start_time = datetime.now(shanghai_tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc).isoformat()

        filter_conditions = {
            "and": [
                {
                    "property": mapping.get('title_property'),
                    "title": {
                        "does_not_contain": "🧘"  # 不包含休息任务
                    }
                },
                {
                    "property": mapping.get('status_property'),
                    "status": {
                        "does_not_equal": "已完成"
                    }
                },
                {
                    "property": mapping.get('status_property'),
                    "status": {
                        "does_not_equal": "已取消"
                    }
                },
                {
                    "property": timebox_start_property,
                    "date": {
                        "on_or_after": today_start_time
                    }
                },
                *(
                    [{
                        "property": schedule_status_property,
                        "select": {
                            "does_not_equal": schedule_status_done_value
                        }
                    }] if schedule_status_todo_value and schedule_status_done_value else []
                ),
                *(
                    [{
                        "property": parent_task_property,
                        "relation": {
                            "is_empty": True
                        }
                    }] if parent_task_property else []
                )
            ]
        }
        sorts_conditions = [
                {
                    "property": priority_property,
                    "direction": "ascending"
                }
            ]
        
        # 查询数据库获取原始任务数据
        pending_tasks_root_level = notion.databases.query(
            database_id=config.database_id,
            filter=filter_conditions,
            sorts=sorts_conditions
        ).get('results', [])
        print(f"🍃 获取到 {len(pending_tasks_root_level)} 个待排程任务")
        return pending_tasks_root_level

    except Exception as e:
        print(f"Error fetching pending tasks: {e}")
        return {}

def process_task_delay(notion, config, mapping, delayed_task_id):
    """
    处理任务延期的核心逻辑
    
    Args:
        notion: NotionClient 实例
        config: 配置对象
        mapping: 属性映射字典
        delayed_task_id: 要延期的任务ID
    
    Returns:
        dict: 操作结果
    """
    try:
        # 获取属性映射
        title_property = mapping.get('title_property')
        timebox_start_property = mapping.get('timebox_start_property')
        parent_task_property = mapping.get('parent_task_property')
        
        # 获取要延期的任务
        delayed_task_raw = notion.pages.retrieve(page_id=delayed_task_id)
        
        # 构建结构化的延期任务对象，提高代码可读性
        delayed_task = {
            'id': delayed_task_id,
            'title': get_task_title(delayed_task_raw, title_property),
            'raw_data': delayed_task_raw,
            'start_time': None,
            'end_time': None
        }
        
        # 解析任务的当前时间信息（延期后的时间）
        if timebox_start_property and timebox_start_property in delayed_task_raw['properties']:
            date_prop = delayed_task_raw['properties'][timebox_start_property]
            if 'date' in date_prop and date_prop['date']:
                start_time_str = date_prop['date']['start']
                end_time_str = date_prop['date'].get('end')
                
                # 使用统一的时间解析函数
                delayed_task['start_time'] = parse_notion_datetime(start_time_str)
                delayed_task['end_time'] = parse_notion_datetime(end_time_str)
        
        # 验证任务是否有结束时间
        if not delayed_task['end_time']:
            return {
                'success': False,
                'error': '任务没有结束时间，无法进行延期操作'
            }
        
        # 获取延期后的结束时间（用于后续计算）
        current_end_datetime = delayed_task['end_time']
        
        # 步骤1：记录延期任务信息（任务本身已在Notion中更新，无需再次更新）
        updated_tasks = []
        updated_tasks.append({
            'id': delayed_task['id'],
            'title': delayed_task['title'],
            'type': '延期任务',
            'old_end_time': '',  # 不显示原时间，因为用户没有提供
            'new_end_time': delayed_task['end_time'].isoformat() if delayed_task['end_time'] else None
        })
        
        # 步骤2：查找并调整有时间冲突的后续任务，并计算延期时长
        conflicting_tasks = find_conflicting_tasks(notion, config, mapping, delayed_task)
        delay_duration = None
        
        if conflicting_tasks:
            # 找到受延期影响的第一个任务（开始时间最早的那个）
            earliest_conflict_task = conflicting_tasks[0]
            # 解析最早冲突任务的开始时间
            earliest_start_time = parse_notion_datetime(earliest_conflict_task['start_time'])
            print(f"🍃 最早冲突任务开始时间: {earliest_start_time}")
            print(earliest_conflict_task['title'])
            # 计算需要延期的时长：延期任务的结束时间 - 受影响的第一个任务的开始时间
            if current_end_datetime > earliest_start_time:
                delay_duration = current_end_datetime - earliest_start_time
            # 步骤3：使用计算出的延期时长来更新父任务
                if delay_duration is not None:
                    print(f"🍃 计算出的延期时长: {delay_duration}")
                    # 更新父任务
                    parent_updates = update_parent_tasks_end_time(notion, config, mapping, delayed_task_id, delay_duration)
                    updated_tasks.extend(parent_updates)

                    # 调整所有冲突的任务
                    conflict_updates = adjust_conflicting_tasks(notion, config, mapping, conflicting_tasks, delay_duration)
                    updated_tasks.extend(conflict_updates)
                else:
                    # 如果没有冲突任务，我们无法准确计算延期时长，但仍可以尝试推算
                    # 这种情况下，我们假设任务被延期到了当前时间，计算一个近似的延期时长
                    shanghai_tz = pytz.timezone('Asia/Shanghai')
                    current_time = datetime.now(shanghai_tz)
                    if current_end_datetime > current_time:
                        # 如果延期后的时间在未来，假设延期时长为30分钟（可调整）
                        delay_duration = timedelta(minutes=30)
                        parent_updates = update_parent_tasks_end_time(notion, config, mapping, delayed_task_id, delay_duration)
                        updated_tasks.extend(parent_updates)
   
                return {
                    'success': True,
                    'affected_tasks': len(updated_tasks),
                    'updated_tasks': updated_tasks,
                    'message': f'成功处理延期任务，共影响 {len(updated_tasks)} 个任务'
                }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def parse_notion_datetime(time_str):
    """
    解析Notion返回的时间字符串，统一处理时区
    
    Args:
        time_str: Notion返回的时间字符串，例如:
                 - "2025-07-04T02:19:00.000Z" (UTC)
                 - "2025-07-04T12:15:00.000+08:00" (带时区)
                 - "2025-07-04T12:15:00.000" (无时区)
    
    Returns:
        datetime: 带时区信息的datetime对象，无时区时默认为UTC
    """
    if not time_str:
        return None
    
    dt = datetime.fromisoformat(time_str)
    # 如果没有时区信息，假设为UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=pytz.utc)
    
    return dt

def get_task_title(task, title_property):
    """获取任务标题"""
    if title_property and title_property in task['properties']:
        title_prop = task['properties'][title_property]
        if 'title' in title_prop and title_prop['title']:
            return title_prop['title'][0]['plain_text']
    return "未命名任务"

def update_task_time_property(notion, task_id, timebox_property, start_time, end_time):
    """更新任务的时间属性"""
    def format_datetime_for_notion(dt):
        """将datetime对象格式化为Notion API需要的格式"""
        if dt is None:
            return None
        if isinstance(dt, str):
            return dt
        # 直接返回ISO格式字符串（datetime对象已有正确时区信息）
        return dt.isoformat()
    
    start_time_str = format_datetime_for_notion(start_time)
    end_time_str = format_datetime_for_notion(end_time)
    
    properties_update = {
        timebox_property: {
            "date": {
                "start": start_time_str,
                "end": end_time_str
            }
        }
    }
    print(f"🍃 更新任务时间属性: {properties_update}")
    try:
        notion.pages.update(
            page_id=task_id,
            properties=properties_update
        )
        print(f"🍃 更新任务时间属性成功: {task_id}")
    except Exception as e:
        print(f"Error updating task time property: {str(e)}")

def update_parent_tasks_end_time(notion, config, mapping, task_id, delay_duration):
    """逐层向上更新父任务的结束时间，使用延期时长"""
    updated_tasks = []
    
    try:
        parent_task_property = mapping.get('parent_task_property')
        timebox_start_property = mapping.get('timebox_start_property')
        title_property = mapping.get('title_property')
        
        if not parent_task_property:
            return updated_tasks
        
        # 获取当前任务
        current_task = notion.pages.retrieve(page_id=task_id)
        
        # 检查是否有父任务
        if parent_task_property not in current_task['properties']:
            return updated_tasks
        
        parent_relations = current_task['properties'][parent_task_property].get('relation', [])
        if not parent_relations:
            return updated_tasks
            
        parent_id = parent_relations[0]['id']
        parent_task = notion.pages.retrieve(page_id=parent_id)
        
        # 获取父任务的当前时间
        parent_start_time = None
        parent_end_time = None
        
        if timebox_start_property and timebox_start_property in parent_task['properties']:
            date_prop = parent_task['properties'][timebox_start_property]
            if 'date' in date_prop and date_prop['date']:
                parent_start_time = date_prop['date']['start']
                parent_end_time = date_prop['date'].get('end')
        
        if parent_end_time:
            # 解析父任务的原结束时间
            original_parent_end_datetime = parse_notion_datetime(parent_end_time)
            
            # 计算父任务的新结束时间 = 原结束时间 + 延期时长
            new_parent_end_datetime = original_parent_end_datetime + delay_duration

            # 更新父任务的结束时间
            update_task_time_property(notion, parent_id, timebox_start_property, parent_start_time, new_parent_end_datetime)
            
            updated_tasks.append({
                'id': parent_id,
                'title': get_task_title(parent_task, title_property),
                'type': '父任务',
                'old_end_time': parent_end_time,
                'new_end_time': new_parent_end_datetime.isoformat()
            })
            
            # 递归更新父任务的父任务，传递相同的延期时长
            parent_updates = update_parent_tasks_end_time(notion, config, mapping, parent_id, delay_duration)
            updated_tasks.extend(parent_updates)

    except Exception as e:
        print(f"Error updating parent tasks: {str(e)}")
    
    return updated_tasks

def find_conflicting_tasks(notion, config, mapping, delayed_task):
    """查找与当前任务结束时间有冲突的后续任务"""
    try:
        timebox_start_property = mapping.get('timebox_start_property')
        title_property = mapping.get('title_property')
        status_property = mapping.get('status_property')
        
        if not timebox_start_property:
            return []
        
        # 计算今天晚上24点的时间（作为筛选的上限）
        today = datetime.now(pytz.timezone('Asia/Shanghai')).date()
        today_midnight = datetime.combine(today, datetime.min.time()) + timedelta(days=1)
        today_midnight = pytz.timezone('Asia/Shanghai').localize(today_midnight)
        
        # 如果延期任务没有开始时间，无法查找冲突任务
        if not delayed_task['start_time']:
            return []
        
        # 查找延期任务后续的任务，且开始时间在今天晚上24点之前的任务
        tasks_response = notion.databases.query(
            database_id=config.database_id,
            filter={
                "and": [
                    {
                        "property": status_property,
                        "status": {
                            "does_not_equal": "已完成"
                        }
                    },
                    {
                        "property": status_property,
                        "status": {
                            "does_not_equal": "已取消"
                        }
                    },
                    {
                        "property": timebox_start_property,
                        "date": {
                            "after": delayed_task['start_time'].isoformat()
                        }
                    },
                    {
                        "property": timebox_start_property,
                        "date": {
                            "before": today_midnight.isoformat()
                        }
                    }
                ]
            },
            sorts=[
                {
                    "property": timebox_start_property,
                    "direction": "ascending"
                }
            ]
        )
        
        tasks = tasks_response.get('results', [])
        conflicting_tasks = []
        
        for task in tasks:
            conflicting_tasks.append({
                'id': task['id'],
                'title': get_task_title(task, title_property),
                'start_time': task['properties'][timebox_start_property]['date']['start'],
                'end_time': task['properties'][timebox_start_property]['date'].get('end')
            })
        return conflicting_tasks
        
    except Exception as e:
        print(f"Error finding conflicting tasks: {str(e)}")
        return []

def adjust_conflicting_tasks(notion, config, mapping, conflicting_tasks, delay_duration):
    """调整冲突任务的时间，延期指定的时长"""
    updated_tasks = []
    
    try:
        timebox_start_property = mapping.get('timebox_start_property')
        
        if not timebox_start_property:
            return updated_tasks
        
        for task in conflicting_tasks:
            try:
                # 获取任务的当前时间
                original_start_time = task['start_time']
                original_end_time = task['end_time']
                
                if original_start_time:
                    # 解析开始时间和结束时间
                    original_start_datetime = parse_notion_datetime(original_start_time)
                    new_start_datetime = original_start_datetime + delay_duration
                    
                    new_end_datetime = None
                    if original_end_time:
                        original_end_datetime = parse_notion_datetime(original_end_time)
                        new_end_datetime = original_end_datetime + delay_duration
                    
                    # 更新任务时间
                    update_task_time_property(notion, task['id'], timebox_start_property, new_start_datetime, new_end_datetime)
                    
                    updated_tasks.append({
                        'id': task['id'],
                        'title': task['title'],
                        'type': '冲突调整',
                        'old_start_time': original_start_time,
                        'new_start_time': new_start_datetime.isoformat(),
                        'old_end_time': original_end_time,
                        'new_end_time': new_end_datetime.isoformat() if new_end_datetime else None
                    })
                    
            except Exception as e:
                print(f"Error adjusting task {task['id']}: {str(e)}")
                continue
    
    except Exception as e:
        print(f"Error adjusting conflicting tasks: {str(e)}")
    
    return updated_tasks



# 装饰器工具：简化配置检查和数据库连接

def require_config(f):
    """装饰器：要求存在有效的配置"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        config = CalendarDatabaseConfig.get_current_config()
        if not config:
            if request.is_json:
                return jsonify({"error": "No configuration found"}), 400
            flash('请先连接 Notion', 'error')
            return redirect(url_for('connect'))
        
        return f(config, *args, **kwargs)
    return decorated_function

def require_database_config(f):
    """装饰器：要求存在有效的配置和数据库设置"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        config = CalendarDatabaseConfig.get_current_config()
        if not config:
            if request.is_json:
                return jsonify({"error": "No configuration found"}), 400
            flash('请先连接 Notion', 'error')
            return redirect(url_for('connect'))
        
        if not config.database_id:
            if request.is_json:
                return jsonify({"error": "Database not configured"}), 400
            flash('请先配置数据库', 'error')
            return redirect(url_for('connect'))
        
        return f(config, *args, **kwargs)
    return decorated_function

def require_notion_client(f):
    """装饰器：要求配置存在并自动创建Notion客户端"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        config = CalendarDatabaseConfig.get_current_config()
        if not config:
            if request.is_json:
                return jsonify({"error": "No configuration found"}), 400
            flash('请先连接 Notion', 'error')
            return redirect(url_for('connect'))
        
        if not config.database_id:
            if request.is_json:
                return jsonify({"error": "Database not configured"}), 400
            flash('请先配置数据库', 'error')
            return redirect(url_for('connect'))
        
        try:
            notion = NotionClient(auth=config.token)
            return f(config, notion, *args, **kwargs)
        except Exception as e:
            if request.is_json:
                return jsonify({"error": f"Failed to connect to Notion: {str(e)}"}), 500
            flash(f'连接 Notion 失败: {str(e)}', 'error')
            return redirect(url_for('connect'))
    return decorated_function

def require_full_setup(f):
    """装饰器：要求完整设置（配置+数据库+客户端+映射）"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        config = CalendarDatabaseConfig.get_current_config()
        if not config:
            if request.is_json:
                return jsonify({"error": "No configuration found"}), 400
            flash('请先连接 Notion', 'error')
            return redirect(url_for('connect'))
        
        if not config.database_id:
            if request.is_json:
                return jsonify({"error": "Database not configured"}), 400
            flash('请先配置数据库', 'error')
            return redirect(url_for('connect'))
        
        try:
            notion = NotionClient(auth=config.token)
            mapping = config.get_property_mapping()
            return f(config, notion, mapping, *args, **kwargs)
        except Exception as e:
            if request.is_json:
                return jsonify({"error": f"Failed to connect to Notion: {str(e)}"}), 500
            flash(f'连接 Notion 失败: {str(e)}', 'error')
            return redirect(url_for('connect'))
    return decorated_function

def require_mapping_setup(f):
    """装饰器：要求排程功能所需的完整映射配置"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        config = CalendarDatabaseConfig.get_current_config()
        if not config:
            flash('请先连接 Notion', 'error')
            return redirect(url_for('connect'))
        
        if not config.database_id:
            flash('请先配置数据库', 'error')
            return redirect(url_for('connect'))
        
        if not config.is_mapping_complete_for_scheduling():
            flash('请先配置数据库的属性映射', 'error')
            return redirect(url_for('property_mapping'))
        
        try:
            notion = NotionClient(auth=config.token)
            mapping = config.get_property_mapping()
            return f(config, notion, mapping, *args, **kwargs)
        except Exception as e:
            flash(f'连接 Notion 失败: {str(e)}', 'error')
            return redirect(url_for('connect'))
    return decorated_function

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Ensure secret key for session support
    if not app.config.get('SECRET_KEY'):
        app.config['SECRET_KEY'] = 'your-secret-key-for-session-support'
    
    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    
    with app.app_context():
        db.create_all()
    
    # Add template context processors
    @app.context_processor
    def utility_processor():
        return {
            'now': datetime.now,
            'format_datetime': lambda dt, format='%Y-%m-%d %H:%M:%S': dt.strftime(format) if dt else ''
        }
    
    @app.route('/')
    def index():
        # Check if there's an active configuration
        config = CalendarDatabaseConfig.get_current_config()
        if config:
            return render_template('index.html', config=config)
        return redirect(url_for('connect'))
    
    @app.route('/connect', methods=['GET', 'POST'])
    def connect():
        # 获取当前配置
        current_config = CalendarDatabaseConfig.get_current_config()
        
        # 初始化状态信息
        integration_status = {
            'has_token': False,
            'token_valid': False,
            'has_database': False,
            'last_updated': None
        }
        
        print("【debug】: current_config", current_config)
        if current_config:
            # 检查现有配置
            integration_status['has_token'] = True
            integration_status['has_database'] = bool(current_config.database_id)
            integration_status['last_updated'] = current_config.updated_at
            
            # 验证token是否仍然有效
            try:
                notion = NotionClient(auth=current_config.token)
                response = notion.search(
                    filter={
                        "value": "database",
                        "property": "object"
                    }
                )
                if 'results' in response:
                    integration_status['token_valid'] = True
                    print("【debug】: Token 有效")
            except Exception as e:
                integration_status['token_valid'] = False
                integration_status['error'] = str(e)
        
        if request.method == 'POST':
            # 处理完整配置提交（token + database_id）
            token = request.form.get('token')
            database_id = request.form.get('database_id')
            
            if not token:
                flash('请提供有效的 Notion API token', 'error')
                return redirect(url_for('connect'))
            
            if not database_id:
                flash('请选择数据库', 'error')
                return redirect(url_for('connect'))
            
            try:
                # 验证token和数据库
                notion = NotionClient(auth=token)
                
                # 先验证token
                db_list_response = notion.search(
                    filter={
                        "value": "database",
                        "property": "object"
                    }
                )
                if 'results' not in db_list_response:
                    flash('无效的 token 或 API 请求失败', 'error')
                    return redirect(url_for('connect'))
                
                # 验证数据库存在且可访问
                db_info = notion.databases.retrieve(database_id=database_id)
                if 'id' not in db_info:
                    flash('无法访问选择的数据库', 'error')
                    return redirect(url_for('connect'))
                
                # 保存完整配置
                if current_config:
                    # 更新现有配置
                    current_config.token = token
                    current_config.database_id = database_id
                    current_config.updated_at = datetime.utcnow()
                    db.session.commit()
                    flash('配置已成功更新！', 'success')
                else:
                    # 创建新配置
                    config = CalendarDatabaseConfig(
                        token=token,
                        database_id=database_id
                    )
                    db.session.add(config)
                    db.session.commit()
                    flash('成功连接到 Notion 并配置数据库！', 'success')
                
                return redirect(url_for('connect'))
                
            except Exception as e:
                flash(f'配置错误: {str(e)}', 'error')
        
        return render_template('connect.html', 
                             integration_status=integration_status,
                             current_config=current_config)
    
    @app.route('/delay', methods=['GET', 'POST'])
    @require_mapping_setup
    def delay(config, notion, mapping):
        """任务延期功能 - 支持选择子任务并更新父任务和后续任务"""
        if request.method == 'POST':
            task_id = request.form.get('task_id')
            
            if not task_id:
                flash('请选择要处理的延期任务', 'error')
                return redirect(url_for('delay'))
            
            try:
                # 执行延期操作
                result = process_task_delay(notion, config, mapping, task_id)
                
                if result['success']:
                    # 保存操作记录
                    operation = TaskOperation(
                        config_id=config.id,
                        database_id=config.database_id,
                        tasks_affected=result.get('affected_tasks', 0),
                        delay_hours=0,  # 新版本不再使用固定延时
                        delay_minutes=0,
                        status='completed'
                    )
                    db.session.add(operation)
                    db.session.commit()
                    
                    # 返回结果页面
                    return render_template('delay_result.html', result=result, config=config)
                else:
                    flash(f'延期操作失败: {result.get("error", "未知错误")}', 'error')
                    
            except ValueError as e:
                flash(f'时间格式错误: {str(e)}', 'error')
            except Exception as e:
                flash(f'延期操作错误: {str(e)}', 'error')
        
        return render_template('delay.html', config=config)
    
    @app.route('/get_property_options/<property_name>')
    @require_notion_client
    def get_property_options(config, notion, property_name):
        try:
            db_info = notion.databases.retrieve(database_id=config.database_id)
            properties = db_info.get('properties', {})
            
            prop_info = properties.get(property_name)
            if not prop_info:
                return jsonify({'error': 'Property not found'}), 404

            options = []
            prop_type = prop_info.get('type')

            if prop_type == 'select':
                options = [opt['name'] for opt in prop_info['select']['options']]
            elif prop_type == 'status':
                options = [opt['name'] for opt in prop_info['status']['options']]
            
            return jsonify(options)

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/property-mapping', methods=['GET', 'POST'])
    @require_notion_client
    def property_mapping(config, notion):
        """配置属性映射关系"""
        
        # 获取数据库的所有属性
        properties = {}
        try:
            db_info = notion.databases.retrieve(database_id=config.database_id)
            if 'properties' in db_info:
                properties = db_info['properties']
        except Exception as e:
            flash(f'获取数据库属性错误: {str(e)}', 'error')

        if request.method == 'POST':
            try:
                # 从表单获取所有提交的数据
                form_data = request.form.to_dict()
                mapping_to_save = {}

                # 遍历所有可能的映射键
                for key in [
                    'title_property', 'priority_property', 'estimated_time_property',
                    'parent_task_property', 'child_task_property', 'status_property',
                    'schedule_status_property', 'timebox_start_property', 'timebox_end_property'
                ]:
                    # 从表单获取选中的属性名称
                    selected_name = form_data.get(key)
                    if selected_name and selected_name in properties:
                        mapping_to_save[key] = selected_name
                    else:
                         mapping_to_save[key] = None
                
                # 单独处理状态值，它们不是ID
                mapping_to_save['schedule_status_todo_value'] = form_data.get('schedule_status_todo_value')
                mapping_to_save['schedule_status_done_value'] = form_data.get('schedule_status_done_value')

                # 使用 set_property_mapping 一次性完整更新
                config.set_property_mapping(mapping_to_save)
                
                db.session.commit()
                flash('属性映射配置成功保存!', 'success')
                return redirect(url_for('connect'))
                
            except Exception as e:
                flash(f'保存映射配置错误: {str(e)}', 'error')
        
        current_mapping = config.get_property_mapping()

        # 如果已经选择了排程状态属性，获取其选项列表
        if current_mapping.get('schedule_status_property'):
            try:
                property_name = current_mapping['schedule_status_property']
                if property_name in properties:
                    prop_info = properties[property_name]
                    prop_type = prop_info.get('type')
                    
                    options = []
                    if prop_type == 'select' and 'select' in prop_info:
                        options = [opt['name'] for opt in prop_info['select']['options']]
                    elif prop_type == 'status' and 'status' in prop_info:
                        options = [opt['name'] for opt in prop_info['status']['options']]
                    
                    # 将选项数据添加到mapping对象中
                    current_mapping['schedule_status_options'] = options
            except Exception as e:
                # 如果获取选项失败，不影响页面正常显示
                print(f"获取排程状态属性选项失败: {str(e)}")
                mapping_for_template['schedule_status_options'] = []

        # 按属性类型分类
        select_properties = {}
        number_properties = {}
        relation_properties = {}
        title_properties = {}
        status_properties = {}
        date_properties = {}
        
        for name, prop in properties.items():
            prop_type = prop.get('type')
            # 使用属性ID作为键，属性信息作为值
            prop_info = prop.copy()
            prop_info['name'] = name  # 保存属性名称以供显示
            
            if prop_type == 'select':
                select_properties[name] = prop_info
            elif prop_type == 'number':
                number_properties[name] = prop_info
            elif prop_type == 'relation':
                relation_properties[name] = prop_info
            elif prop_type == 'title':
                title_properties[name] = prop_info
            elif prop_type == 'status':
                status_properties[name] = prop_info
            elif prop_type == 'date':
                date_properties[name] = prop_info
        
        return render_template('property_mapping.html', 
                             config=config, 
                             mapping=current_mapping,
                             properties=properties,
                             select_properties=select_properties,
                             number_properties=number_properties,
                             relation_properties=relation_properties,
                             title_properties=title_properties,
                             status_properties=status_properties,
                             date_properties=date_properties,
                             properties_json=json.dumps(properties))
    
    @app.route('/api/database/property/<property_id>/options', methods=['GET'])
    @require_notion_client
    def api_database_property_options(config, notion, property_id):
        try:
            db_info = notion.databases.retrieve(database_id=config.database_id)
            properties = db_info.get('properties', {})
            
            # Find property by ID by iterating over the dict's values
            prop_to_check = next((prop for prop in properties.values() if prop['id'] == property_id), None)
            
            if not prop_to_check:
                return jsonify({"error": "Property not found"}), 404
            
            prop_type = prop_to_check.get('type')
            
            options = []
            if prop_type == 'select' and 'select' in prop_to_check:
                options = [opt['name'] for opt in prop_to_check['select']['options']]
            elif prop_type == 'status' and 'status' in prop_to_check:
                options = [opt['name'] for opt in prop_to_check['status']['options']]
            
            return jsonify({"options": options})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/schedule', methods=['GET'])
    @require_mapping_setup
    def schedule(config, notion, mapping):
        """批量安排日程页面"""
        def round_time_to_5_minutes(dt):
            """将时间向上取整到5分钟的倍数"""
            minutes = dt.minute
            rounded_minutes = math.ceil(minutes / 5) * 5
            
            # 处理分钟数超过60的情况
            if rounded_minutes >= 60:
                dt = dt.replace(minute=0) + timedelta(hours=1)
            else:
                dt = dt.replace(minute=rounded_minutes, second=0, microsecond=0)
            
            return dt
        
        # 默认起始时间为当前时间后5分钟，并向上取整到5分钟倍数  
        shanghai_tz = pytz.timezone('Asia/Shanghai')
        current_time = datetime.now(shanghai_tz) + timedelta(minutes=5)
        rounded_start_time = round_time_to_5_minutes(current_time)
        # 转换为本地时间字符串（不带时区信息，供HTML input使用）
        default_start_time = rounded_start_time.replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M")
        
        return render_template('schedule.html', config=config, default_start_time=default_start_time)
    
    @app.route('/schedule', methods=['POST'])
    @require_mapping_setup
    def schedule_tasks(config, notion, mapping):
        try:
            # 获得待排序的根任务列表
            pending_root_tasks = get_pending_tasks(config, notion, mapping)
            
            # 构建任务树（格式化 + 递归子任务）
            task_tree = build_task_tree_with_formatting(notion, config, mapping, pending_root_tasks)
            
            # 开始排程
            # 初始化日程安排的时间游标
            start_time_str = request.form.get('start_time')
            if not start_time_str:
                flash('请设置起始时间', 'error')
                return redirect(url_for('schedule'))
            try:
                # 解析用户输入的本地时间（不带时区信息）
                raw_start_time_naive = datetime.fromisoformat(start_time_str)
                
                # 将本地时间设置为上海时区
                shanghai_tz = pytz.timezone('Asia/Shanghai')
                raw_start_time = shanghai_tz.localize(raw_start_time_naive)
                
                # 将用户输入的时间也对齐到5分钟倍数
                def round_time_to_5_minutes(dt):
                    """将时间向上取整到5分钟的倍数，保持时区信息"""
                    minutes = dt.minute
                    rounded_minutes = math.ceil(minutes / 5) * 5
                    
                    # 处理分钟数超过60的情况
                    if rounded_minutes >= 60:
                        dt = dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                    else:
                        dt = dt.replace(minute=rounded_minutes, second=0, microsecond=0)
                    
                    return dt
                
                start_time = round_time_to_5_minutes(raw_start_time)
                # 如果时间被调整了，给用户一个友好提示
                if start_time != raw_start_time:
                    original_time = raw_start_time.strftime("%H:%M")
                    adjusted_time = start_time.strftime("%H:%M")
                    flash(f'开始时间已自动调整为5分钟倍数：{original_time} → {adjusted_time}', 'info')
                
            except ValueError:
                flash('无效的起始时间格式', 'error')
                return redirect(url_for('schedule'))
            
            # 工具函数，给定page ID 和 开始、结束时间，调用 notion SDK，更新任务的开始和结束时间
            def update_task_time(page_id, start_time, end_time):
                """
                更新任务的开始和结束时间到Notion
                
                Args:
                    page_id: Notion页面ID
                    start_time: 开始时间 (datetime对象)
                    end_time: 结束时间 (datetime对象)
                
                Returns:
                    bool: 更新是否成功
                """
                try:
                    timebox_start_property_name = mapping.get('timebox_start_property')
                    timebox_end_property_name = mapping.get('timebox_end_property')
                    schedule_status_property_name = mapping.get('schedule_status_property')
                    schedule_status_done_value = mapping.get('schedule_status_done_value')

                    # 转换为ISO格式字符串
                    start_time_iso = start_time.isoformat()
                    end_time_iso = end_time.isoformat()
                    
                    # 如果开始和结束时间是同一个字段，就只更新一个
                    if timebox_start_property_name == timebox_end_property_name:
                        notion.pages.update(
                            page_id=page_id, 
                            properties={
                                timebox_start_property_name: {
                                    'date': {
                                        'start': start_time_iso,
                                        'end': end_time_iso
                                    }
                                },
                                schedule_status_property_name: {
                                    'select': {
                                        'name': schedule_status_done_value
                                    }
                                }
                            }
                        )
                    else:
                        # 分别更新开始和结束时间字段
                        properties_to_update = {
                            schedule_status_property_name: {
                                'select': {
                                    'name': schedule_status_done_value
                                }
                            }
                        }
                        
                        if timebox_start_property_name:
                            properties_to_update[timebox_start_property_name] = {
                                'date': {
                                    'start': start_time_iso
                                }
                            }
                        
                        if timebox_end_property_name:
                            properties_to_update[timebox_end_property_name] = {
                                'date': {
                                    'start': end_time_iso
                                }
                            }
                        
                        if properties_to_update:
                            notion.pages.update(
                                page_id=page_id,
                                properties=properties_to_update
                            )
                    
                    return True
                    
                except Exception as e:
                    print(f"❌ 更新任务 {page_id} 时间失败: {str(e)}")
                    return False

            # 定义工具函数，按照顺序按照叶节点和兄弟节点的开始和结束时间
            def schedule_task_tree(task_tree, start_time, continuous_work_minutes=0, rest_tasks_to_create=None):
                """
                递归地为任务树安排时间，让同级任务首尾相连，并自动插入休息时间
                
                Args:
                    task_tree: 任务树列表
                    start_time: 开始时间
                    continuous_work_minutes: 持续工作时间（分钟），在递归调用间传递
                    rest_tasks_to_create: 用于收集需要创建的休息任务信息的列表
                    
                Returns:
                    tuple: (结束时间, 更新后的持续工作时间)
                """
                if rest_tasks_to_create is None:
                    rest_tasks_to_create = []
                
                def round_up_to_5_minutes(minutes):
                    """向上取整到5的倍数，确保时间安排更加规整"""
                    if minutes <= 0:
                        return 5  # 最少5分钟
                    return math.ceil(minutes / 5) * 5
                
                current_time = start_time
                
                for task in task_tree:
                    if task.get('scheduled', False):
                        continue
                    
                    # 如果有子任务，先安排子任务
                    if task.get('children') and len(task['children']) > 0:
                        # 子任务从当前时间开始，传递当前的持续工作时间
                        child_end_time, updated_work_minutes = schedule_task_tree(task['children'], current_time, continuous_work_minutes, rest_tasks_to_create)
                        # 父任务的时间跨度覆盖所有子任务
                        task['start_time'] = current_time
                        task['end_time'] = child_end_time
                        task['scheduled'] = True
                        current_time = child_end_time
                        continuous_work_minutes = updated_work_minutes
                    else:
                        # 叶子任务：直接安排时间，使用向上取整的时间
                        estimated_time = task['estimated_time']
                        rounded_time = round_up_to_5_minutes(estimated_time)
                        task['start_time'] = current_time
                        task['end_time'] = current_time + timedelta(minutes=rounded_time)
                        task['scheduled'] = True
                        current_time = task['end_time']
                        # 更新持续工作时间
                        continuous_work_minutes += rounded_time
                        
                        # 检查是否需要插入休息时间
                        if continuous_work_minutes > 45:
                            
                            # 准备休息时间的开始和结束时间
                            rest_start_time = current_time
                            rest_end_time = current_time + timedelta(minutes=15)  # 15分钟休息
                            
                            # 确定父任务ID（如果当前任务有父任务，则使用相同的父任务）
                            parent_task_id = None
                            if task.get('parent_tasks') and len(task['parent_tasks']) > 0:
                                # parent_tasks是一个包含关系对象的列表，每个对象都有id字段
                                parent_task_id = task['parent_tasks'][0].get('id')
                            
                            # 获取当前任务的优先级
                            task_priority = task.get('priority', 'P3')
                            
                            # 收集休息任务信息，不直接创建
                            rest_task_info = {
                                'parent_task_id': parent_task_id,
                                'priority': task_priority,
                                'start_time': rest_start_time,
                                'end_time': rest_end_time,
                                'title': '🧘 休息时间',
                                'estimated_time': 15
                            }
                            rest_tasks_to_create.append(rest_task_info)
                            
                            # 更新current_time到休息结束时间
                            current_time = rest_end_time
                            # 重置持续工作时间计数器
                            continuous_work_minutes = 0
                                        
                return current_time, continuous_work_minutes
            
            # 检查是否是预览模式
            is_preview = request.form.get('preview') == 'true'
            
            # 准备休息任务收集列表
            rest_tasks_info = []
            
            # 执行排程
            final_end_time, total_work_minutes = schedule_task_tree(task_tree, start_time, 0, rest_tasks_info)
            print(f"🎯 排程完成，总工作时间: {total_work_minutes} 分钟")
            
            if rest_tasks_info:
                print(f"🧘 收集到 {len(rest_tasks_info)} 个休息任务")
            
            if is_preview:
                # 预览模式：只返回排程结果，不更新Notion
                # 将任务树数据存储到session中，供确认时使用
                from flask import session
                import pickle
                import base64
                
                # 序列化任务树数据并存储到session
                task_tree_data = {
                    'task_tree': task_tree,
                    'start_time': start_time.isoformat(),
                    'config_id': config.id,
                    'rest_tasks_info': rest_tasks_info
                }
                serialized_data = base64.b64encode(pickle.dumps(task_tree_data)).decode('utf-8')
                session['schedule_preview'] = serialized_data
                
                # 统计信息
                def count_tasks(tasks):
                    count = 0
                    for task in tasks:
                        if task.get('scheduled', False):
                            count += 1
                        if task.get('children'):
                            count += count_tasks(task['children'])
                    return count
                
                total_tasks = count_tasks(task_tree)
                
                # 为JavaScript准备JSON安全的任务树数据
                def prepare_task_tree_for_json(tasks):
                    """将任务树中的datetime对象转换为字符串，便于JSON序列化"""
                    json_safe_tasks = []
                    for task in tasks:
                        json_task = task.copy()
                        
                        # 转换datetime对象为ISO字符串
                        if isinstance(json_task.get('start_time'), datetime):
                            json_task['start_time'] = json_task['start_time'].isoformat()
                        if isinstance(json_task.get('end_time'), datetime):
                            json_task['end_time'] = json_task['end_time'].isoformat()
                        
                        # 递归处理子任务
                        if json_task.get('children'):
                            json_task['children'] = prepare_task_tree_for_json(json_task['children'])
                        
                        json_safe_tasks.append(json_task)
                    
                    return json_safe_tasks
                
                json_safe_task_tree = prepare_task_tree_for_json(task_tree)
                
                # 渲染预览页面
                return render_template('schedule_preview.html', 
                                     config=config,
                                     task_tree=task_tree,
                                     json_task_tree=json_safe_task_tree,
                                     start_time=start_time,
                                     total_tasks=total_tasks,
                                     rest_tasks_count=len(rest_tasks_info),
                                     rest_tasks_info=rest_tasks_info)
            else:
                # 确认模式：执行实际的Notion更新
                # 删除当天的所有休息任务
                delete_today_rest_tasks(notion, config, mapping)
                
                # 定义创建休息任务的函数
                def create_rest_task(rest_task_info):
                    """在Notion中创建休息任务"""
                    try:
                        # 准备休息任务的属性
                        properties = {}
                        
                        # 设置标题
                        title_property = mapping.get('title_property')
                        if title_property:
                            properties[title_property] = {
                                'title': [
                                    {
                                        'text': {
                                            'content': rest_task_info['title']
                                        }
                                    }
                                ]
                            }
                        
                        # 设置优先级
                        priority_property = mapping.get('priority_property')
                        if priority_property and rest_task_info.get('priority'):
                            properties[priority_property] = {
                                'select': {
                                    'name': rest_task_info['priority']
                                }
                            }
                        
                        # 设置父任务关系（只有在有父任务ID时才设置）
                        parent_task_property = mapping.get('parent_task_property')
                        if parent_task_property and rest_task_info.get('parent_task_id'):
                            properties[parent_task_property] = {
                                'relation': [
                                    {
                                        'id': rest_task_info['parent_task_id']
                                    }
                                ]
                            }
                        
                        # 设置预估时间
                        estimated_time_property = mapping.get('estimated_time_property')
                        if estimated_time_property:
                            properties[estimated_time_property] = {
                                'number': rest_task_info.get('estimated_time', 15)
                            }
                        
                        # 设置时间范围
                        timebox_start_property = mapping.get('timebox_start_property')
                        timebox_end_property = mapping.get('timebox_end_property')
                        
                        # 确保时间带有时区信息
                        shanghai_tz = pytz.timezone('Asia/Shanghai')
                        rest_start_time = rest_task_info['start_time']
                        rest_end_time = rest_task_info['end_time']
                        
                        if rest_start_time.tzinfo is None:
                            rest_start_time = shanghai_tz.localize(rest_start_time)
                        if rest_end_time.tzinfo is None:
                            rest_end_time = shanghai_tz.localize(rest_end_time)
                        
                        # 如果开始和结束时间是同一个字段
                        if timebox_start_property == timebox_end_property and timebox_start_property:
                            properties[timebox_start_property] = {
                                'date': {
                                    'start': rest_start_time.isoformat(),
                                    'end': rest_end_time.isoformat()
                                }
                            }
                        else:
                            # 分别设置开始和结束时间
                            if timebox_start_property:
                                properties[timebox_start_property] = {
                                    'date': {
                                        'start': rest_start_time.isoformat()
                                    }
                                }
                            if timebox_end_property:
                                properties[timebox_end_property] = {
                                    'date': {
                                        'start': rest_end_time.isoformat()
                                    }
                                }
                        
                        # 创建休息任务页面
                        response = notion.pages.create(
                            parent={'database_id': config.database_id},
                            properties=properties
                        )
                        
                        print(f"✅ 成功创建休息任务: {response.get('id')}")
                        return response.get('id')
                        
                    except Exception as e:
                        print(f"❌ 创建休息任务失败: {str(e)}")
                        return None
                
                # 递归更新任务树中所有任务的时间到Notion
                def update_task_tree_to_notion(tasks):
                    """递归更新任务树中所有任务的时间到Notion"""
                    success_count = 0
                    total_count = 0
                    
                    for task in tasks:
                        if task.get('scheduled', False) and task.get('start_time') and task.get('end_time'):
                            total_count += 1
                            if update_task_time(task['id'], task['start_time'], task['end_time']):
                                success_count += 1
                        
                        # 递归处理子任务
                        if task.get('children'):
                            child_success, child_total = update_task_tree_to_notion(task['children'])
                            success_count += child_success
                            total_count += child_total
                    
                    return success_count, total_count
                
                # 更新所有任务到Notion
                try:
                    success_count, total_count = update_task_tree_to_notion(task_tree)
                    
                    # 创建休息任务
                    rest_tasks_created = 0
                    if rest_tasks_info:
                        print(f"🧘 开始创建 {len(rest_tasks_info)} 个休息任务...")
                        for rest_info in rest_tasks_info:
                            rest_task_id = create_rest_task(rest_info)
                            if rest_task_id:
                                rest_tasks_created += 1
                        print(f"🎯 成功创建了 {rest_tasks_created}/{len(rest_tasks_info)} 个休息任务")
                    
                    # 将休息任务计入总数
                    total_count += len(rest_tasks_info)
                    success_count += rest_tasks_created
                    
                    # 保存排程操作记录
                    operation = ScheduleOperation(
                        config_id=config.id,
                        database_id=config.database_id,
                        tasks_scheduled=success_count,
                        start_time=start_time,
                        status='completed' if success_count == total_count else 'partial'
                    )
                    db.session.add(operation)
                    db.session.commit()
                    
                    # 准备结果页面数据
                    result_data = {
                        'success_count': success_count,
                        'total_count': total_count,
                        'start_time': start_time,
                        'operation_id': operation.id,
                        'status': operation.status,
                        'completion_time': datetime.now(pytz.timezone('Asia/Shanghai'))
                    }
                    
                    # 根据更新结果跳转到不同页面
                    if success_count == total_count:
                        # 完全成功，跳转到成功结果页面
                        return render_template('schedule_success.html', 
                                             config=config,
                                             result=result_data)
                    elif success_count > 0:
                        # 部分成功，也跳转到结果页面但显示警告信息
                        flash(f'⚠️ 部分成功：{success_count}/{total_count} 个任务已安排日程，其余任务更新失败', 'warning')
                        return render_template('schedule_success.html', 
                                             config=config,
                                             result=result_data)
                    else:
                        # 完全失败，返回原页面并显示错误
                        flash(f'❌ 日程安排失败：无法更新任务时间到Notion，请检查网络连接和权限', 'error')
                        return redirect(url_for('schedule'))
                        
                except Exception as e:
                    flash(f'❌ 日程安排出错: {str(e)}', 'error')
                    return redirect(url_for('schedule'))
            
        except Exception as e:
            flash(f'安排任务错误: {str(e)}', 'error')
            return redirect(url_for('schedule'))
    
    @app.route('/schedule/confirm', methods=['POST'])
    @require_mapping_setup
    def confirm_schedule(config, notion, mapping):
        """确认并执行日程安排"""
        try:
            from flask import session
            import pickle
            import base64
            
            # 从session中获取预览数据
            if 'schedule_preview' not in session:
                flash('❌ 预览数据已过期，请重新生成排程', 'error')
                return redirect(url_for('schedule'))
            
            # 反序列化任务树数据
            serialized_data = session['schedule_preview']
            task_tree_data = pickle.loads(base64.b64decode(serialized_data.encode('utf-8')))
            
            task_tree = task_tree_data['task_tree']
            rest_tasks_info = task_tree_data.get('rest_tasks_info', [])
            
            # 恢复带时区的开始时间
            start_time_str = task_tree_data['start_time']
            shanghai_tz = pytz.timezone('Asia/Shanghai')
            
            # 如果存储的时间没有时区信息，添加上海时区
            if '+' in start_time_str or 'Z' in start_time_str:
                # 已有时区信息的情况
                start_time = datetime.fromisoformat(start_time_str)
                if start_time.tzinfo is None:
                    start_time = shanghai_tz.localize(start_time)
                else:
                    # 转换到上海时区
                    start_time = start_time.astimezone(shanghai_tz)
            else:
                # 无时区信息，视为本地时间
                start_time_naive = datetime.fromisoformat(start_time_str)
                start_time = shanghai_tz.localize(start_time_naive)
            
            # 重新定义update_task_time函数（因为在不同scope）
            def update_task_time(page_id, start_time, end_time):
                """更新任务的开始和结束时间到Notion"""
                try:
                    timebox_start_property_name = mapping.get('timebox_start_property')
                    timebox_end_property_name = mapping.get('timebox_end_property')
                    
                    # 确保时间带有时区信息，转换为ISO格式字符串
                    shanghai_tz = pytz.timezone('Asia/Shanghai')
                    
                    # 如果时间没有时区信息，添加上海时区
                    if start_time.tzinfo is None:
                        start_time = shanghai_tz.localize(start_time)
                    if end_time.tzinfo is None:
                        end_time = shanghai_tz.localize(end_time)
                    
                    # 转换为ISO格式字符串（Notion API格式）
                    start_time_iso = start_time.isoformat()
                    end_time_iso = end_time.isoformat()
                    
                    # 如果开始和结束时间是同一个字段，就只更新一个
                    if timebox_start_property_name == timebox_end_property_name:
                        notion.pages.update(
                            page_id=page_id, 
                            properties={
                                timebox_start_property_name: {
                                    'date': {
                                        'start': start_time_iso,
                                        'end': end_time_iso
                                    }
                                }
                            }
                        )
                    else:
                        # 分别更新开始和结束时间字段
                        properties_to_update = {}
                        
                        if timebox_start_property_name:
                            properties_to_update[timebox_start_property_name] = {
                                'date': {
                                    'start': start_time_iso
                                }
                            }
                        
                        if timebox_end_property_name:
                            properties_to_update[timebox_end_property_name] = {
                                'date': {
                                    'start': end_time_iso
                                }
                            }
                        
                        if properties_to_update:
                            notion.pages.update(
                                page_id=page_id,
                                properties=properties_to_update
                            )
                    
                    return True
                    
                except Exception as e:
                    print(f"❌ 更新任务 {page_id} 时间失败: {str(e)}")
                    return False
            
            # 递归更新任务树中所有任务的时间到Notion
            def update_task_tree_to_notion(tasks):
                """递归更新任务树中所有任务的时间到Notion"""
                success_count = 0
                total_count = 0
                
                for task in tasks:
                    if task.get('scheduled', False) and task.get('start_time') and task.get('end_time'):
                        total_count += 1
                        if update_task_time(task['id'], task['start_time'], task['end_time']):
                            success_count += 1
                    
                    # 递归处理子任务
                    if task.get('children'):
                        child_success, child_total = update_task_tree_to_notion(task['children'])
                        success_count += child_success
                        total_count += child_total
                
                return success_count, total_count
            
            # 定义创建休息任务的函数
            def create_rest_task(rest_task_info):
                """在Notion中创建休息任务"""
                try:
                    # 准备休息任务的属性
                    properties = {}
                    
                    # 设置标题
                    title_property = mapping.get('title_property')
                    if title_property:
                        properties[title_property] = {
                            'title': [
                                {
                                    'text': {
                                        'content': rest_task_info.get('title', '🧘 休息时间')
                                    }
                                }
                            ]
                        }
                    
                    # 设置优先级
                    priority_property = mapping.get('priority_property')
                    if priority_property and rest_task_info.get('priority'):
                        properties[priority_property] = {
                            'select': {
                                'name': rest_task_info['priority']
                            }
                        }
                    
                    # 设置父任务关系（只有在有父任务ID时才设置）
                    parent_task_property = mapping.get('parent_task_property')
                    if parent_task_property and rest_task_info.get('parent_task_id'):
                        properties[parent_task_property] = {
                            'relation': [
                                {
                                    'id': rest_task_info['parent_task_id']
                                }
                            ]
                        }
                    
                    # 设置预估时间
                    estimated_time_property = mapping.get('estimated_time_property')
                    if estimated_time_property:
                        properties[estimated_time_property] = {
                            'number': rest_task_info.get('estimated_time', 15)
                        }
                    
                    # 设置时间范围
                    timebox_start_property = mapping.get('timebox_start_property')
                    timebox_end_property = mapping.get('timebox_end_property')
                    
                    # 确保时间带有时区信息
                    rest_start_time = rest_task_info['start_time']
                    rest_end_time = rest_task_info['end_time']
                    
                    if rest_start_time.tzinfo is None:
                        rest_start_time = shanghai_tz.localize(rest_start_time)
                    if rest_end_time.tzinfo is None:
                        rest_end_time = shanghai_tz.localize(rest_end_time)
                    
                    # 如果开始和结束时间是同一个字段
                    if timebox_start_property == timebox_end_property and timebox_start_property:
                        properties[timebox_start_property] = {
                            'date': {
                                'start': rest_start_time.isoformat(),
                                'end': rest_end_time.isoformat()
                            }
                        }
                    else:
                        # 分别设置开始和结束时间
                        if timebox_start_property:
                            properties[timebox_start_property] = {
                                'date': {
                                    'start': rest_start_time.isoformat()
                                }
                            }
                        if timebox_end_property:
                            properties[timebox_end_property] = {
                                'date': {
                                    'start': rest_end_time.isoformat()
                                }
                            }
                    
                    # 创建休息任务页面
                    response = notion.pages.create(
                        parent={'database_id': config.database_id},
                        properties=properties
                    )
                    
                    print(f"✅ 成功创建休息任务: {response.get('id')}")
                    return response.get('id')
                    
                except Exception as e:
                    print(f"❌ 创建休息任务失败: {str(e)}")
                    return None
            
            # 删除当天的所有休息任务
            delete_today_rest_tasks(notion, config, mapping)
            
            # 执行实际的Notion更新
            success_count, total_count = update_task_tree_to_notion(task_tree)
            
            # 创建休息任务
            rest_tasks_created = 0
            if rest_tasks_info:
                print(f"🧘 开始创建 {len(rest_tasks_info)} 个休息任务...")
                for rest_info in rest_tasks_info:
                    rest_task_id = create_rest_task(rest_info)
                    if rest_task_id:
                        rest_tasks_created += 1
                print(f"🎯 成功创建了 {rest_tasks_created}/{len(rest_tasks_info)} 个休息任务")
            
            # 将休息任务计入总数
            total_count += len(rest_tasks_info)
            success_count += rest_tasks_created
            
            # 保存排程操作记录
            operation = ScheduleOperation(
                config_id=config.id,
                database_id=config.database_id,
                tasks_scheduled=success_count,
                start_time=start_time,
                status='completed' if success_count == total_count else 'partial'
            )
            db.session.add(operation)
            db.session.commit()
            
            # 清除session中的预览数据
            session.pop('schedule_preview', None)
            
            # 准备结果页面数据
            result_data = {
                'success_count': success_count,
                'total_count': total_count,
                'start_time': start_time,
                'operation_id': operation.id,
                'status': operation.status,
                'completion_time': datetime.now(pytz.timezone('Asia/Shanghai'))
            }
            
            # 根据更新结果跳转到不同页面
            if success_count == total_count:
                # 完全成功，跳转到成功结果页面
                return render_template('schedule_success.html', 
                                     config=config,
                                     result=result_data)
            elif success_count > 0:
                # 部分成功，也跳转到结果页面但显示警告信息
                flash(f'⚠️ 部分成功：{success_count}/{total_count} 个任务已安排日程，其余任务更新失败', 'warning')
                return render_template('schedule_success.html', 
                                     config=config,
                                     result=result_data)
            else:
                # 完全失败，返回原页面并显示错误
                flash(f'❌ 日程安排失败：无法更新任务时间到Notion，请检查网络连接和权限', 'error')
                return redirect(url_for('schedule'))
            
        except Exception as e:
            flash(f'❌ 确认日程安排出错: {str(e)}', 'error')
            return redirect(url_for('schedule'))
    
    @app.route('/schedule/cancel', methods=['POST'])
    def cancel_schedule():
        """取消预览并清除session数据"""
        from flask import session
        session.pop('schedule_preview', None)
        flash('📋 预览已取消', 'info')
        return redirect(url_for('schedule'))
    
    @app.route('/api/databases', methods=['GET'])
    @require_config
    def api_databases(config):
        try:
            notion = NotionClient(auth=config.token)
            response = notion.search(
                filter={
                    "value": "database",
                    "property": "object"
                }
            )
            return jsonify(response)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/database/properties', methods=['GET'])
    @require_notion_client
    def api_database_properties(config, notion):
        try:
            response = notion.databases.retrieve(database_id=config.database_id)
            
            # Extract only the properties
            properties = response.get('properties', {})
            
            # Filter for date properties only
            date_properties = {k: v for k, v in properties.items() if v.get('type') == 'date'}
            
            return jsonify({"properties": date_properties})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    
    @app.route('/api/database/pending-tasks', methods=['GET'])
    @require_full_setup
    def api_database_pending_tasks(config, notion, mapping):
        """获取数据库中的待排程任务列表"""
        try:
            
            # 先获取数据库属性信息，用于名称转ID
            notion = NotionClient(auth=config.token)
            db_info = notion.databases.retrieve(database_id=config.database_id)
            properties = db_info.get('properties', {})
            
            # 创建属性名称到ID的映射
            name_to_id = {name: prop['id'] for name, prop in properties.items()}
            
            # 获取属性名称并转换为ID（用于API过滤）
            timebox_property_name = mapping.get('timebox_start_property')
            parent_task_property_name = mapping.get('parent_task_property')
            schedule_status_property_name = mapping.get('schedule_status_property')
            schedule_status_done_value = mapping.get('schedule_status_done_value')
            
            # 转换为ID
            timebox_property_id = name_to_id.get(timebox_property_name) if timebox_property_name else None
            parent_task_property_id = name_to_id.get(parent_task_property_name) if parent_task_property_name else None
            schedule_status_property_id = name_to_id.get(schedule_status_property_name) if schedule_status_property_name else None

            shanghai_tz = pytz.timezone('Asia/Shanghai')
            today_start_time = datetime.now(shanghai_tz).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(pytz.utc).isoformat()

            filter_conditions = {
                "and": [
                    {
                        "property": timebox_property_id,
                        "date": {
                            "on_or_after": today_start_time
                        }
                    },
                    *(
                        [{
                            "property": schedule_status_property_id,
                            "select": {
                                "does_not_equal": schedule_status_done_value
                            }
                        }] if schedule_status_property_id and schedule_status_done_value else []
                    ),
                    *(
                        [{
                            "property": parent_task_property_id,
                            "relation": {
                                "is_empty": True
                            }
                        }] if parent_task_property_id else []
                    )
                ]
            }

            # 获取待排程任务
            pending_tasks = notion.databases.query(
                **{
                    "database_id": config.database_id,
                    "filter": filter_conditions,
                }
            )['results']

            # # 一步到位获取标题内容
            # title_response = notion.pages.properties.retrieve(page_id=pending_tasks[0]['id'], property_id='title')
            # title_content = title_response['results'][0]['title']['plain_text']

            # 从映射中获取属性名称
            title_property_name = mapping.get('title_property')
            priority_property_name = mapping.get('priority_property')
            estimated_time_property_name = mapping.get('estimated_time_property')
            child_task_property_name = mapping.get('child_task_property')
            
            # 获得 task 对象的属性值
            formatted_tasks = []
            total_estimated_time = 0
            for task in pending_tasks:
                title = task['properties'].get(title_property_name, {}).get('title', [{}])[0].get('plain_text', '')
                priority = task['properties'].get(priority_property_name, {}).get('select', {}).get('name', '')
                estimated_time = task['properties'].get(estimated_time_property_name, {}).get('number', 0) or 0
                children_count = len(task['properties'].get(child_task_property_name, {}).get('relation', []))
                has_children = children_count > 0
                total_estimated_time += estimated_time
                formatted_tasks.append({
                    "id": task['id'],
                    "title": title,
                    "priority": priority,
                    "estimated_time": estimated_time,
                    "children_count": children_count,
                    "has_children": has_children
                })
            
            return jsonify({
                "success": True,
                "tasks": formatted_tasks,
                "total_tasks": len(pending_tasks),
                "total_estimated_time": total_estimated_time
            })
            
        except Exception as e:
            return jsonify({"error": f"获取任务失败: {str(e)}"}), 500

    @app.route('/api/leaf-tasks', methods=['GET'])
    @require_mapping_setup
    def api_leaf_tasks(config, notion, mapping):
        """API端点：获取叶节点任务（没有子任务的任务）"""
        try:
            # 获取所有任务（包括有开始时间的任务）
            timebox_start_property = mapping.get('timebox_start_property')
            if not timebox_start_property:
                return jsonify({
                    'success': False,
                    'error': '未配置时间盒开始属性'
                }), 400
            
            # 查询所有有开始时间的任务
            tasks_response = notion.databases.query(
                database_id=config.database_id,
                filter={
                    "property": timebox_start_property,
                    "date": {
                        "is_not_empty": True
                    }
                }
            )
            
            all_tasks = tasks_response.get('results', [])
            
            # 找出叶节点任务（没有子任务的任务）
            leaf_tasks = []
            parent_task_property = mapping.get('parent_task_property')
            
            if parent_task_property:
                # 如果有父任务属性，通过检查是否有子任务来确定叶节点
                parent_ids = set()
                for task in all_tasks:
                    if parent_task_property in task['properties']:
                        parent_relations = task['properties'][parent_task_property].get('relation', [])
                        for parent_relation in parent_relations:
                            parent_ids.add(parent_relation['id'])
                
                # 叶节点 = 所有任务 - 有子任务的任务
                for task in all_tasks:
                    if task['id'] not in parent_ids:
                        leaf_tasks.append(task)
            else:
                # 如果没有父任务属性，则将所有任务视为叶节点
                leaf_tasks = all_tasks
            
            # 格式化任务信息
            formatted_tasks = []
            title_property = mapping.get('title_property')
            
            for task in leaf_tasks:
                task_title = "未命名任务"
                if title_property and title_property in task['properties']:
                    title_prop = task['properties'][title_property]
                    if 'title' in title_prop and title_prop['title']:
                        task_title = title_prop['title'][0]['plain_text']
                
                formatted_tasks.append({
                    'id': task['id'],
                    'title': task_title
                })
            
            return jsonify({
                'success': True,
                'tasks': formatted_tasks
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

    @app.route('/api/task-details/<task_id>', methods=['GET'])
    @require_mapping_setup
    def api_task_details(config, notion, mapping, task_id):
        """API端点：获取任务详情"""
        try:
            # 获取任务详情
            task = notion.pages.retrieve(page_id=task_id)
            
            # 提取任务信息
            title_property = mapping.get('title_property')
            timebox_start_property = mapping.get('timebox_start_property')
            parent_task_property = mapping.get('parent_task_property')
            
            # 获取任务标题
            task_title = "未命名任务"
            if title_property and title_property in task['properties']:
                title_prop = task['properties'][title_property]
                if 'title' in title_prop and title_prop['title']:
                    task_title = title_prop['title'][0]['plain_text']
            
            # 获取时间信息
            start_time = None
            end_time = None
            if timebox_start_property and timebox_start_property in task['properties']:
                date_prop = task['properties'][timebox_start_property]
                if 'date' in date_prop and date_prop['date']:
                    start_time = date_prop['date']['start']
                    end_time = date_prop['date'].get('end')
            
            # 获取父任务信息
            parent_task = None
            if parent_task_property and parent_task_property in task['properties']:
                parent_relations = task['properties'][parent_task_property].get('relation', [])
                if parent_relations:
                    # 获取第一个父任务的信息
                    parent_id = parent_relations[0]['id']
                    parent_task_obj = notion.pages.retrieve(page_id=parent_id)
                    if title_property and title_property in parent_task_obj['properties']:
                        parent_title_prop = parent_task_obj['properties'][title_property]
                        if 'title' in parent_title_prop and parent_title_prop['title']:
                            parent_task = parent_title_prop['title'][0]['plain_text']
            
            return jsonify({
                'success': True,
                'task': {
                    'id': task_id,
                    'title': task_title,
                    'start_time': start_time,
                    'end_time': end_time,
                    'parent_task': parent_task
                }
            })
            
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    @app.route('/reset-config', methods=['POST'])
    def reset_config():
        """重置配置（删除当前配置）"""
        config = CalendarDatabaseConfig.get_current_config()
        if config:
            db.session.delete(config)
            db.session.commit()
            flash('配置已重置', 'success')
        return redirect(url_for('connect'))
    
    @app.route('/validate-mapping', methods=['GET'])
    def validate_mapping():
        """验证和修复属性映射"""
        config = CalendarDatabaseConfig.get_current_config()
        if not config:
            flash('没有找到配置', 'error')
            return redirect(url_for('connect'))
        
        try:
            notion = NotionClient(auth=config.token)
            
            # 验证属性映射（简化版本，因为现在直接存储名称）
            db_info = notion.databases.retrieve(database_id=config.database_id)
            properties = db_info.get('properties', {})
            mapping = config.get_property_mapping()
            
            issues = []
            for key, value in mapping.items():
                if value and not key.endswith('_value'):  # 排除状态值字段
                    if value not in properties:
                        issues.append(f"属性 '{key}' 的值 '{value}' 在数据库中不存在")
            
            if len(issues) == 0:
                flash('属性映射验证通过！所有属性都存在于数据库中', 'success')
            else:
                flash(f'属性映射存在问题：{"; ".join(issues)}', 'warning')
            
        except Exception as e:
            flash(f'验证过程中出错: {str(e)}', 'error')
        
        return redirect(url_for('connect'))
    
    @app.route('/fix-mapping', methods=['POST'])
    def fix_mapping():
        """自动修复属性映射"""
        config = CalendarDatabaseConfig.get_current_config()
        if not config:
            flash('没有找到配置', 'error')
            return redirect(url_for('connect'))
        
        try:
            notion = NotionClient(auth=config.token)
            
            # 修复属性映射（简化版本，因为现在直接存储名称）
            db_info = notion.databases.retrieve(database_id=config.database_id)
            properties = db_info.get('properties', {})
            mapping = config.get_property_mapping().copy()
            
            fixed_count = 0
            issues = []
            
            for key, value in mapping.items():
                if value and not key.endswith('_value'):  # 排除状态值字段
                    if value not in properties:
                        # 尝试通过ID找到正确的属性名称
                        found_name = None
                        for prop_name, prop_info in properties.items():
                            if prop_info.get('id') == value:
                                found_name = prop_name
                                break
                        
                        if found_name:
                            mapping[key] = found_name
                            fixed_count += 1
                            issues.append(f"已修复 '{key}': 从ID '{value}' 转换为名称 '{found_name}'")
                        else:
                            issues.append(f"无法修复 '{key}': 值 '{value}' 既不是有效的名称也不是有效的ID")
            
            if fixed_count > 0:
                config.set_property_mapping(mapping)
                db.session.commit()
                flash(f'属性映射修复完成！修复了 {fixed_count} 个属性。详情：{"; ".join(issues)}', 'success')
            else:
                flash('属性映射已经是正确的，无需修复', 'info')
            
        except Exception as e:
            flash(f'修复过程中出错: {str(e)}', 'error')
        
        return redirect(url_for('connect'))
    
    @app.route('/api/validate-token', methods=['POST'])
    def api_validate_token():
        """验证 Notion API Token 并获取可用数据库列表"""
        data = request.get_json()
        token = data.get('token')
        
        if not token:
            return jsonify({"error": "Token is required"}), 400
        
        try:
            notion = NotionClient(auth=token)
            response = notion.search(
                filter={
                    "value": "database",
                    "property": "object"
                }
            )
            
            if 'results' in response:
                return jsonify({
                    "valid": True,
                    "databases": response.get('results', [])
                })
            else:
                return jsonify({
                    "valid": False,
                    "error": "Invalid token or API request failed"
                })
        except Exception as e:
            return jsonify({
                "valid": False,
                "error": str(e)
            }), 500
    
    @app.route('/schedule_history', methods=['GET'])
    def schedule_history():
        """显示日程操作历史"""
        operations = ScheduleOperation.query.all()
        return render_template('schedule_history.html', operations=operations)
    
    return app

app = create_app()

@app.cli.command("clean-config")
def clean_config():
    """Deletes all existing configuration data from the database."""
    try:
        # Since operations have foreign keys to the config, they must be deleted first.
        num_task_ops = db.session.query(TaskOperation).delete()
        num_schedule_ops = db.session.query(ScheduleOperation).delete()
        num_configs = db.session.query(CalendarDatabaseConfig).delete()
        
        db.session.commit()
        
        print(f"Successfully deleted:")
        print(f"- {num_configs} configuration(s)")
        print(f"- {num_task_ops} task operation record(s)")
        print(f"- {num_schedule_ops} schedule operation record(s)")
        print("Database configuration has been cleared.")
        
    except Exception as e:
        db.session.rollback()
        print(f"An error occurred: {e}")

def build_task_tree_with_formatting(notion_client, config, mapping, root_tasks):
    """
    构建完整的任务树，包含格式化和子任务递归
    
    Args:
        notion_client: Notion API 客户端
        config: 配置对象，包含 database_id
        mapping: 属性映射字典
        root_tasks: 根任务列表
    
    Returns:
        格式化后的任务树列表
    """
    
    def format_task(task):
        """格式化单个任务对象"""
        # 获取所有属性映射
        timebox_start_property = mapping.get('timebox_start_property')
        timebox_end_property = mapping.get('timebox_end_property')
        schedule_status_property = mapping.get('schedule_status_property')
        schedule_status_todo_value = mapping.get('schedule_status_todo_value')
        schedule_status_done_value = mapping.get('schedule_status_done_value')
        parent_task_property = mapping.get('parent_task_property')
        priority_property = mapping.get('priority_property')
        child_task_property = mapping.get('child_task_property')
        estimated_time_property = mapping.get('estimated_time_property')
        title_property = mapping.get('title_property')
        status_property = mapping.get('status_property')
        date_property = mapping.get('date_property')
        
        # 安全获取 properties，处理可能的 None 值
        properties = task.get('properties', {}) or {}
        
        # 定义安全的字段获取函数
        def safe_get_text(prop_name):
            """安全获取文本属性"""
            try:
                if not prop_name:
                    return ''
                prop_data = properties.get(prop_name, {}) or {}
                title_list = prop_data.get('title', []) or []
                if not title_list:
                    return ''
                first_item = title_list[0] if isinstance(title_list, list) and title_list else {}
                return (first_item or {}).get('plain_text', '')
            except (AttributeError, TypeError, IndexError):
                return ''
        
        def safe_get_select(prop_name):
            """安全获取选择属性"""
            try:
                if not prop_name:
                    return ''
                prop_data = properties.get(prop_name, {}) or {}
                select_data = prop_data.get('select', {}) or {}
                return select_data.get('name', '')
            except (AttributeError, TypeError):
                return ''
        
        def safe_get_status(prop_name):
            """安全获取状态属性"""
            try:
                if not prop_name:
                    return ''
                prop_data = properties.get(prop_name, {}) or {}
                status_data = prop_data.get('status', {}) or {}
                return status_data.get('name', '')
            except (AttributeError, TypeError):
                return ''
        
        def safe_get_number(prop_name):
            """安全获取数字属性"""
            try:
                if not prop_name:
                    return 0
                prop_data = properties.get(prop_name, {}) or {}
                return prop_data.get('number', 0) or 0
            except (AttributeError, TypeError):
                return 0
        
        def safe_get_date(prop_name, field='start'):
            """安全获取日期属性"""
            try:
                if not prop_name:
                    return ''
                prop_data = properties.get(prop_name, {}) or {}
                date_data = prop_data.get('date', {}) or {}
                return date_data.get(field, '')
            except (AttributeError, TypeError):
                return ''
        
        def safe_get_relation(prop_name):
            """安全获取关系属性"""
            try:
                if not prop_name:
                    return []
                prop_data = properties.get(prop_name, {}) or {}
                relation_data = prop_data.get('relation', []) or []
                return relation_data if isinstance(relation_data, list) else []
            except (AttributeError, TypeError):
                return []
        
        return {
            'id': task.get('id', ''),
            'name': safe_get_text(title_property),
            'priority': safe_get_select(priority_property),
            'estimated_time': safe_get_number(estimated_time_property),
            'start_time': safe_get_date(timebox_start_property, 'start'),
            'end_time': safe_get_date(timebox_end_property, 'end'),
            'status': safe_get_status(status_property),
            'schedule_status': safe_get_status(schedule_status_property),
            'parent_tasks': safe_get_relation(parent_task_property),
            'date': safe_get_date(date_property, 'start'),
            'sorted': False
        }
    
    def get_child_tasks_sorted_by_priority(page_id):
        """获取指定父任务的排序子任务列表"""
        try:
            data = notion_client.databases.query(
                database_id=config.database_id,
                filter={
                    "and": [
                        {
                            "property": mapping.get('parent_task_property'),
                            "relation": {
                                "contains": page_id
                            }
                        },
                        {
                            "property": mapping.get('title_property'),
                            "title": {
                                "does_not_contain": "🧘"  # 不包含休息任务
                            }
                        }
                    ]
                },
                sorts=[
                    {
                        "property": mapping.get('priority_property'),
                        "direction": "ascending"
                    }
                ]
            ).get('results', [])
            
            if len(data) == 0:
                return []
            
            # 格式化所有子任务
            return [format_task(task) for task in data]
        except Exception as e:
            print(f"DEBUG❌❌❌❌❌❌ 获取子任务失败: {e}")
            return []
    
    def get_child_task_tree(parent_task):
        """递归构建子任务树"""
        # 获取排序后的直接子任务
        child_tasks = get_child_tasks_sorted_by_priority(parent_task['id'])
        if not child_tasks:
            return []
        
        # 为每个子任务递归构建其子任务树
        for child_task in child_tasks:
            child_task['children'] = get_child_task_tree(child_task)
        
        return child_tasks
    
    # 主函数逻辑：构建完整的任务树
    try:
        # 首先格式化所有根任务
        formatted_root_tasks = [format_task(task) for task in root_tasks]
        
        # 为每个根任务构建子任务树
        for task in formatted_root_tasks:
            task['children'] = get_child_task_tree(task)
        
        return formatted_root_tasks
        
    except Exception as e:
        print(f"DEBUG❌❌❌❌❌❌ 构建任务树失败: {e}")
        return []

if __name__ == '__main__':
    app.run(debug=True)
