#!/usr/bin/env python3
"""
历史记录验证工具 - 验证 Agent Kernel 的全量历史记录功能

验证内容：
1. SQLite 数据库完整性
2. requests 表 - 请求历史
3. tasks 表 - 任务历史
4. events 表 - 事件日志
5. snapshots 表 - 执行快照
6. sessions 表 - 会话历史
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


class Colors:
    """ANSI 颜色代码"""
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def print_header(title: str) -> None:
    """打印标题"""
    print(f"{Colors.BLUE}{title}{Colors.NC}")


def print_success(message: str) -> None:
    """打印成功消息"""
    print(f"  {Colors.GREEN}✓{Colors.NC} {message}")


def print_error(message: str) -> None:
    """打印错误消息"""
    print(f"  {Colors.RED}✗{Colors.NC} {message}")


def print_warning(message: str) -> None:
    """打印警告消息"""
    print(f"  {Colors.YELLOW}!{Colors.NC} {message}")


class HistoryValidator:
    """历史记录验证器"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: sqlite3.Connection | None = None
        self.results: dict[str, Any] = {}
        
    def connect(self) -> bool:
        """连接数据库"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            return True
        except sqlite3.Error as e:
            print_error(f"无法连接数据库: {e}")
            return False
    
    def close(self) -> None:
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
    
    def validate_database_exists(self) -> bool:
        """验证数据库文件存在"""
        print_header("验证数据库文件")
        
        if not self.db_path.exists():
            print_error(f"数据库文件不存在: {self.db_path}")
            return False
        
        size = self.db_path.stat().st_size
        print_success(f"数据库文件存在: {self.db_path}")
        print(f"  文件大小: {size:,} 字节")
        return True
    
    def validate_tables(self) -> bool:
        """验证核心表是否存在"""
        print_header("验证数据库表")
        
        required_tables = [
            'sessions',
            'requests', 
            'tasks',
            'snapshots',
            'events',
            'queue',
            'scheduler'
        ]
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = {row[0] for row in cursor.fetchall()}
        
        all_exist = True
        for table in required_tables:
            if table in existing_tables:
                print_success(f"表 '{table}' 存在")
            else:
                print_error(f"表 '{table}' 不存在")
                all_exist = False
        
        return all_exist
    
    def validate_sessions(self) -> dict[str, Any]:
        """验证会话记录"""
        print_header("验证 sessions 表")
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sessions;")
        count = cursor.fetchone()[0]
        
        cursor.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT 5;")
        sessions = cursor.fetchall()
        
        print_success(f"共有 {count} 个会话记录")
        
        if sessions:
            print("  最近的会话:")
            for session in sessions:
                data = json.loads(session['data'])
                print(f"    - {session['id'][:8]}...: 用户 {data.get('user_id', 'N/A')}")
        
        return {'count': count, 'recent': sessions}
    
    def validate_requests(self) -> dict[str, Any]:
        """验证请求记录"""
        print_header("验证 requests 表")
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM requests;")
        count = cursor.fetchone()[0]
        
        cursor.execute("SELECT * FROM requests ORDER BY created_at DESC LIMIT 5;")
        requests = cursor.fetchall()
        
        print_success(f"共有 {count} 个请求记录")
        
        # 统计状态
        cursor.execute("""
            SELECT 
                json_extract(data, '$.status') as status,
                COUNT(*) as count
            FROM requests
            GROUP BY status;
        """)
        status_counts = cursor.fetchall()
        
        if status_counts:
            print("  请求状态分布:")
            for row in status_counts:
                status = row['status'] or 'unknown'
                print(f"    - {status}: {row['count']} 个")
        
        if requests:
            print("  最近的请求:")
            for req in requests:
                data = json.loads(req['data'])
                status = data.get('status', 'unknown')
                message = data.get('message', '')[:30]
                print(f"    - {req['id'][:8]}...: [{status}] {message}...")
        
        return {'count': count, 'status_counts': status_counts, 'recent': requests}
    
    def validate_tasks(self) -> dict[str, Any]:
        """验证任务记录"""
        print_header("验证 tasks 表")
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tasks;")
        count = cursor.fetchone()[0]
        
        if count == 0:
            print_warning("没有任务记录（调度器可能未触发）")
            return {'count': 0}
        
        cursor.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT 5;")
        tasks = cursor.fetchall()
        
        print_success(f"共有 {count} 个任务记录")
        
        # 统计状态
        cursor.execute("""
            SELECT 
                json_extract(data, '$.status') as status,
                COUNT(*) as count
            FROM tasks
            GROUP BY status;
        """)
        status_counts = cursor.fetchall()
        
        if status_counts:
            print("  任务状态分布:")
            for row in status_counts:
                status = row['status'] or 'unknown'
                print(f"    - {status}: {row['count']} 个")
        
        if tasks:
            print("  最近的任务:")
            for task in tasks:
                data = json.loads(task['data'])
                status = data.get('status', 'unknown')
                goal = data.get('goal', '')[:30]
                print(f"    - {task['id'][:8]}...: [{status}] {goal}...")
        
        return {'count': count, 'status_counts': status_counts, 'recent': tasks}
    
    def validate_events(self) -> dict[str, Any]:
        """验证事件记录"""
        print_header("验证 events 表")
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM events;")
        count = cursor.fetchone()[0]
        
        if count == 0:
            print_warning("没有事件记录")
            return {'count': 0}
        
        cursor.execute("SELECT * FROM events ORDER BY id DESC LIMIT 10;")
        events = cursor.fetchall()
        
        print_success(f"共有 {count} 个事件记录")
        
        # 统计事件类型
        cursor.execute("""
            SELECT 
                json_extract(data, '$.phase') as phase,
                COUNT(*) as count
            FROM events
            GROUP BY phase;
        """)
        phase_counts = cursor.fetchall()
        
        if phase_counts:
            print("  事件阶段分布:")
            for row in phase_counts:
                phase = row['phase'] or 'unknown'
                print(f"    - {phase}: {row['count']} 个")
        
        if events:
            print("  最近的事件:")
            for event in events[:5]:
                data = json.loads(event['data'])
                phase = data.get('phase', 'unknown')
                actor = data.get('actor', 'unknown')
                summary = data.get('summary', '')[:25]
                print(f"    - [{phase}] {actor}: {summary}...")
        
        return {'count': count, 'phase_counts': phase_counts, 'recent': events}
    
    def validate_snapshots(self) -> dict[str, Any]:
        """验证快照记录"""
        print_header("验证 snapshots 表")
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM snapshots;")
        count = cursor.fetchone()[0]
        
        if count == 0:
            print_warning("没有快照记录")
            return {'count': 0}
        
        cursor.execute("SELECT * FROM snapshots ORDER BY created_at DESC LIMIT 5;")
        snapshots = cursor.fetchall()
        
        print_success(f"共有 {count} 个快照记录")
        
        if snapshots:
            print("  最近的快照:")
            for snap in snapshots:
                data = json.loads(snap['data'])
                task_id = data.get('task_id', 'N/A')[:8]
                print(f"    - {snap['id'][:8]}...: 任务 {task_id}...")
        
        return {'count': count, 'recent': snapshots}
    
    def validate_indexes(self) -> bool:
        """验证索引"""
        print_header("验证数据库索引")
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
        indexes = {row[0] for row in cursor.fetchall()}
        
        expected_indexes = [
            'idx_requests_session',
            'idx_tasks_session',
            'idx_snapshots_session',
            'idx_events_session',
            'idx_scheduler_trigger'
        ]
        
        all_exist = True
        for idx in expected_indexes:
            if idx in indexes:
                print_success(f"索引 '{idx}' 存在")
            else:
                print_warning(f"索引 '{idx}' 不存在")
                all_exist = False
        
        return all_exist
    
    def generate_report(self) -> None:
        """生成验证报告"""
        print_header("=" * 50)
        print_header("历史记录验证总结")
        print_header("=" * 50)
        
        total_records = (
            self.results.get('sessions', {}).get('count', 0) +
            self.results.get('requests', {}).get('count', 0) +
            self.results.get('tasks', {}).get('count', 0) +
            self.results.get('events', {}).get('count', 0) +
            self.results.get('snapshots', {}).get('count', 0)
        )
        
        print(f"\n总记录数: {total_records}")
        print(f"  - Sessions:  {self.results.get('sessions', {}).get('count', 0)}")
        print(f"  - Requests:  {self.results.get('requests', {}).get('count', 0)}")
        print(f"  - Tasks:     {self.results.get('tasks', {}).get('count', 0)}")
        print(f"  - Events:    {self.results.get('events', {}).get('count', 0)}")
        print(f"  - Snapshots: {self.results.get('snapshots', {}).get('count', 0)}")
        
        # 检查是否有数据
        has_data = total_records > 0
        
        if has_data:
            print(f"\n{Colors.GREEN}✓ 历史记录验证通过{Colors.NC}")
        else:
            print(f"\n{Colors.RED}✗ 未找到历史记录数据{Colors.NC}")
        
    def run(self) -> int:
        """运行完整验证流程"""
        print(f"\n{Colors.BLUE}开始验证历史记录...{Colors.NC}\n")
        
        # 1. 验证数据库存在
        if not self.validate_database_exists():
            return 1
        
        # 2. 连接数据库
        if not self.connect():
            return 1
        
        try:
            # 3. 验证表结构
            if not self.validate_tables():
                print_warning("部分表缺失，继续验证...")
            
            # 4. 验证各个表的数据
            self.results['sessions'] = self.validate_sessions()
            self.results['requests'] = self.validate_requests()
            self.results['tasks'] = self.validate_tasks()
            self.results['events'] = self.validate_events()
            self.results['snapshots'] = self.validate_snapshots()
            
            # 5. 验证索引
            self.validate_indexes()
            
            # 6. 生成报告
            self.generate_report()
            
        finally:
            self.close()
        
        # 返回退出码
        return 0 if self.results.get('requests', {}).get('count', 0) > 0 else 1


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='验证 Agent Kernel 的历史记录功能',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 验证默认路径的数据库
  python3 verify-history.py
  
  # 指定数据目录
  python3 verify-history.py --data-path /path/to/data
  
  # 指定数据库文件
  python3 verify-history.py --db-path /path/to/runtime.db
        """
    )
    
    parser.add_argument(
        '--data-path',
        type=str,
        default='./data',
        help='数据目录路径 (默认: ./data)'
    )
    
    parser.add_argument(
        '--db-path',
        type=str,
        help='数据库文件路径 (覆盖 --data-path)'
    )
    
    args = parser.parse_args()
    
    # 确定数据库路径
    if args.db_path:
        db_path = Path(args.db_path)
    else:
        db_path = Path(args.data_path) / 'runtime.db'
    
    # 运行验证
    validator = HistoryValidator(db_path)
    exit_code = validator.run()
    
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
