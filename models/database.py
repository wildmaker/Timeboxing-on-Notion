from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json

db = SQLAlchemy()

class CalendarDatabaseConfig(db.Model):
    """日历数据库配置表 - 整合所有 Notion 配置"""
    __tablename__ = 'calendar_database_config'
    
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(500), nullable=False, unique=True)
    database_id = db.Column(db.String(100), nullable=False, unique=True)
    property_mapping = db.Column(db.JSON, nullable=True, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联的操作记录
    task_operations = db.relationship('TaskOperation', backref='config', lazy=True, cascade='all, delete-orphan')
    schedule_operations = db.relationship('ScheduleOperation', backref='config', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<CalendarDatabaseConfig {self.database_id}>'
    
    def get_property_mapping(self):
        """获取属性映射字典"""
        return self.property_mapping or {}
    
    def set_property_mapping(self, mapping_dict):
        """设置属性映射"""
        self.property_mapping = mapping_dict
        self.updated_at = datetime.utcnow()
    
    def update_property_mapping(self, **kwargs):
        """更新属性映射的部分字段"""
        current_mapping = self.get_property_mapping()
        for key, value in kwargs.items():
            if value:  # 只更新非空值
                current_mapping[key] = value
            elif key in current_mapping:
                # 如果传入空值，删除该字段
                del current_mapping[key]
        self.set_property_mapping(current_mapping)
    
    def is_mapping_complete_for_scheduling(self):
        """检查映射是否完整，可用于智能排程"""
        mapping = self.get_property_mapping()
        # 'timebox_start_property' is required for date filtering and updating.
        # 'schedule_status_property' and 'schedule_status_todo_value' are for filtering tasks to schedule.
        required_fields = [
            'title_property', 
            'timebox_start_property', 
            'schedule_status_property', 
            'schedule_status_todo_value'
        ]
        return all(mapping.get(field) for field in required_fields)
    
    def get_mapped_property(self, property_type):
        """获取指定类型的映射属性"""
        mapping = self.get_property_mapping()
        return mapping.get(property_type)
    
    def get_mapped_property_id(self, property_type):
        """获取指定类型的映射属性ID（确保返回的是ID而非名称）"""
        return self.get_mapped_property(property_type)
    
# validate_property_mapping 和 fix_property_mapping 方法已被移除
    # 这些功能现在直接在 app.py 的路由中实现，不再依赖 NotionAPI 类
    
    @staticmethod
    def get_current_config():
        """获取当前配置（应该只有一条记录）"""
        return CalendarDatabaseConfig.query.first()

class TaskOperation(db.Model):
    """任务操作记录表"""
    __tablename__ = 'task_operation'
    
    id = db.Column(db.Integer, primary_key=True)
    config_id = db.Column(db.Integer, db.ForeignKey('calendar_database_config.id'), nullable=False)
    database_id = db.Column(db.String(100), nullable=False)  # 冗余字段，便于查询
    tasks_affected = db.Column(db.Integer, default=0)
    delay_hours = db.Column(db.Integer, default=0)
    delay_minutes = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<TaskOperation {self.id}: {self.tasks_affected} tasks>'

class ScheduleOperation(db.Model):
    """排程操作记录表"""
    __tablename__ = 'schedule_operation'
    
    id = db.Column(db.Integer, primary_key=True)
    config_id = db.Column(db.Integer, db.ForeignKey('calendar_database_config.id'), nullable=False)
    database_id = db.Column(db.String(100), nullable=False)  # 冗余字段，便于查询
    tasks_scheduled = db.Column(db.Integer, default=0)
    start_time = db.Column(db.DateTime, nullable=False)
    include_breaks = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ScheduleOperation {self.id}: {self.tasks_scheduled} tasks>'

