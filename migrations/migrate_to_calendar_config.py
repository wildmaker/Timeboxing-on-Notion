#!/usr/bin/env python3
"""
数据迁移脚本：从旧的多表结构迁移到新的 CalendarDatabaseConfig 单表结构

运行方式：
python migrations/migrate_to_calendar_config.py

迁移步骤：
1. 从旧表中读取数据
2. 合并 NotionIntegration + DatabaseConfig + PropertyMapping
3. 创建新的 CalendarDatabaseConfig 记录
4. 迁移操作记录的外键关联
5. 清理旧表（可选）
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from models.database import db, CalendarDatabaseConfig, NotionIntegration, DatabaseConfig, PropertyMapping, TaskOperation, ScheduleOperation
import json

def migrate_data():
    """执行数据迁移"""
    app = create_app()
    
    with app.app_context():
        print("🚀 开始数据迁移...")
        
        # 1. 创建新表
        print("📋 创建新表结构...")
        db.create_all()
        
        # 2. 检查是否已有新配置数据
        existing_config = CalendarDatabaseConfig.query.first()
        if existing_config:
            print(f"⚠️  已存在配置: {existing_config.database_id}")
            response = input("是否覆盖现有配置？(y/N): ")
            if response.lower() != 'y':
                print("❌ 迁移已取消")
                return
            else:
                # 删除现有配置
                CalendarDatabaseConfig.query.delete()
                db.session.commit()
        
        # 3. 查找旧数据
        print("🔍 查找旧数据...")
        old_integrations = NotionIntegration.query.all()
        
        if not old_integrations:
            print("ℹ️  未找到需要迁移的数据")
            return
        
        migrated_count = 0
        
        for integration in old_integrations:
            print(f"📤 处理 Integration ID: {integration.id}")
            
            # 获取关联的数据库配置
            database_configs = DatabaseConfig.query.filter_by(integration_id=integration.id).all()
            
            if not database_configs:
                print(f"⚠️  Integration {integration.id} 没有关联的数据库配置")
                continue
            
            # 如果有多个数据库配置，选择第一个作为主配置
            if len(database_configs) > 1:
                print(f"⚠️  发现多个数据库配置，将迁移第一个: {database_configs[0].database_id}")
            
            primary_db_config = database_configs[0]
            
            # 获取属性映射
            property_mapping = PropertyMapping.query.filter_by(database_config_id=primary_db_config.id).first()
            
            # 构建属性映射 JSON
            mapping_json = {}
            if property_mapping:
                mapping_json = {
                    'title_property': property_mapping.title_property,
                    'priority_property': property_mapping.priority_property,
                    'estimated_time_property': property_mapping.estimated_time_property,
                    'parent_task_property': property_mapping.parent_task_property,
                    'child_task_property': property_mapping.child_task_property,
                    'status_property': property_mapping.status_property,
                    'schedule_status_property': property_mapping.schedule_status_property,
                    'schedule_status_todo_value': property_mapping.schedule_status_todo_value,
                    'schedule_status_done_value': property_mapping.schedule_status_done_value,
                    'timebox_start_property': property_mapping.timebox_start_property,
                    'timebox_end_property': property_mapping.timebox_end_property,
                }
                # 移除空值
                mapping_json = {k: v for k, v in mapping_json.items() if v}
            
            # 创建新的配置记录
            new_config = CalendarDatabaseConfig(
                token=integration.token,
                database_id=primary_db_config.database_id,
                property_mapping=mapping_json,
                created_at=integration.created_at,
                updated_at=primary_db_config.updated_at
            )
            
            db.session.add(new_config)
            db.session.flush()  # 获取新记录的 ID
            
            print(f"✅ 创建新配置: {new_config.database_id}")
            
            # 4. 迁移操作记录
            print("📋 迁移操作记录...")
            
            # 迁移任务操作记录
            task_ops = TaskOperation.query.filter_by(database_id=primary_db_config.database_id).all()
            for op in task_ops:
                op.config_id = new_config.id
            
            # 迁移排程操作记录
            schedule_ops = ScheduleOperation.query.filter_by(database_id=primary_db_config.database_id).all()
            for op in schedule_ops:
                op.config_id = new_config.id
            
            print(f"✅ 迁移了 {len(task_ops)} 个任务操作和 {len(schedule_ops)} 个排程操作")
            
            migrated_count += 1
        
        # 5. 提交变更
        try:
            db.session.commit()
            print(f"🎉 迁移成功！共迁移了 {migrated_count} 个配置")
        except Exception as e:
            db.session.rollback()
            print(f"❌ 迁移失败: {str(e)}")
            return
        
        # 6. 询问是否清理旧表
        print("\n🗑️  数据迁移完成，是否清理旧表？")
        print("注意：这将永久删除以下表的数据：")
        print("- notion_integration")
        print("- database_config")  
        print("- property_mapping")
        
        response = input("确认清理旧表？(y/N): ")
        if response.lower() == 'y':
            cleanup_old_tables()
        
        print("\n✨ 数据迁移完成！")

def cleanup_old_tables():
    """清理旧表数据"""
    print("🧹 清理旧表数据...")
    
    try:
        # 删除表数据（保留表结构）
        PropertyMapping.query.delete()
        DatabaseConfig.query.delete()
        NotionIntegration.query.delete()
        
        db.session.commit()
        print("✅ 旧表数据清理完成")
        
        # 可选：删除表结构
        print("\n是否同时删除旧表结构？")
        response = input("这将完全移除旧表 (y/N): ")
        if response.lower() == 'y':
            try:
                db.engine.execute("DROP TABLE IF EXISTS property_mapping;")
                db.engine.execute("DROP TABLE IF EXISTS database_config;")
                db.engine.execute("DROP TABLE IF EXISTS notion_integration;")
                print("✅ 旧表结构删除完成")
            except Exception as e:
                print(f"⚠️  删除表结构时出现错误: {str(e)}")
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ 清理失败: {str(e)}")

def verify_migration():
    """验证迁移结果"""
    app = create_app()
    
    with app.app_context():
        print("🔍 验证迁移结果...")
        
        configs = CalendarDatabaseConfig.query.all()
        print(f"📊 新表中有 {len(configs)} 个配置记录")
        
        for config in configs:
            print(f"  - 数据库 ID: {config.database_id}")
            print(f"    Token: {config.token[:20]}...")
            print(f"    属性映射字段数: {len(config.get_property_mapping())}")
            print(f"    任务操作记录: {len(config.task_operations)}")
            print(f"    排程操作记录: {len(config.schedule_operations)}")
            print()

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='迁移到新的 CalendarDatabaseConfig 结构')
    parser.add_argument('--verify', action='store_true', help='只验证迁移结果')
    parser.add_argument('--cleanup', action='store_true', help='只清理旧表')
    
    args = parser.parse_args()
    
    if args.verify:
        verify_migration()
    elif args.cleanup:
        app = create_app()
        with app.app_context():
            cleanup_old_tables()
    else:
        migrate_data()