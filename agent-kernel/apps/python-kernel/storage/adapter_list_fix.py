# 修复列表方法
import re

with open('adapter.py', 'r') as f:
    content = f.read()

# 修复 list_requests_by_session - 创建同步版本
old_requests = '''    async def list_requests_by_session(self, session_id: str) -> List[dict]:
        requests: List[dict] = []
        for file_path in (self.base_path / 'requests').glob('*.json'):
            request = await self._read_json(file_path)
            if request and request.get('session_id') == session_id:
                requests.append(request)
        return sorted(requests, key=lambda item: item.get('created_at', ''), reverse=True)'''

new_requests = '''    def _list_requests_sync(self, session_id: str) -> List[dict]:
        requests: List[dict] = []
        for file_path in (self.base_path / 'requests').glob('*.json'):
            request = self._read_json_sync(file_path)
            if request and request.get('session_id') == session_id:
                requests.append(request)
        return sorted(requests, key=lambda item: item.get('created_at', ''), reverse=True)

    async def list_requests_by_session(self, session_id: str) -> List[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._list_requests_sync, session_id)'''

content = content.replace(old_requests, new_requests)

# 修复 list_tasks_by_session
old_tasks = '''    async def list_tasks_by_session(self, session_id: str) -> List[dict]:
        tasks: List[dict] = []
        for file_path in (self.base_path / 'tasks').glob('*.json'):
            task = await self._read_json(file_path)
            if task and task.get('session_id') == session_id:
                tasks.append(task)
        return sorted(tasks, key=lambda item: item.get('created_at', ''), reverse=True)'''

new_tasks = '''    def _list_tasks_sync(self, session_id: str) -> List[dict]:
        tasks: List[dict] = []
        for file_path in (self.base_path / 'tasks').glob('*.json'):
            task = self._read_json_sync(file_path)
            if task and task.get('session_id') == session_id:
                tasks.append(task)
        return sorted(tasks, key=lambda item: item.get('created_at', ''), reverse=True)

    async def list_tasks_by_session(self, session_id: str) -> List[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._list_tasks_sync, session_id)'''

content = content.replace(old_tasks, new_tasks)

# 修复 list_snapshots_by_session
old_snapshots = '''    async def list_snapshots_by_session(self, session_id: str) -> List[dict]:
        snapshots: List[dict] = []
        for file_path in (self.base_path / 'snapshots').glob('*.json'):
            snapshot = await self._read_json(file_path)
            if snapshot and snapshot.get('session_id') == session_id:
                snapshots.append(snapshot)
        return sorted(snapshots, key=lambda item: item.get('created_at', ''), reverse=True)'''

new_snapshots = '''    def _list_snapshots_sync(self, session_id: str) -> List[dict]:
        snapshots: List[dict] = []
        for file_path in (self.base_path / 'snapshots').glob('*.json'):
            snapshot = self._read_json_sync(file_path)
            if snapshot and snapshot.get('session_id') == session_id:
                snapshots.append(snapshot)
        return sorted(snapshots, key=lambda item: item.get('created_at', ''), reverse=True)

    async def list_snapshots_by_session(self, session_id: str) -> List[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, self._list_snapshots_sync, session_id)'''

content = content.replace(old_snapshots, new_snapshots)

with open('adapter.py', 'w') as f:
    f.write(content)

print("✅ 已修复列表方法")
