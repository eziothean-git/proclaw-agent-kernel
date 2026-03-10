"""
Skill Adapters - Adapt MCP-style skills for LocalSkillRegistry
"""
from skills.fs_skill import FileSystemSkill
from skills.shell_skill import ShellSkill


class FileSystemSkillAdapter:
    """Adapter to make FileSystemSkill work with LocalSkillRegistry"""
    
    def __init__(self, allowed_paths=None):
        self.skill = FileSystemSkill(allowed_paths)
    
    async def read_file(self, path: str):
        """Read file contents"""
        result = await self.skill._read_file(path)
        return {"success": True, "content": result[0].text if result else "", "error": None}
    
    async def write_file(self, path: str, content: str):
        """Write file contents"""
        result = await self.skill._write_file(path, content)
        return {"success": True, "result": result[0].text if result else "", "error": None}
    
    async def list_directory(self, path: str):
        """List directory contents"""
        result = await self.skill._list_directory(path)
        return {"success": True, "result": result[0].text if result else "", "error": None}


class ShellSkillAdapter:
    """Adapter to make ShellSkill work with LocalSkillRegistry"""
    
    def __init__(self):
        self.skill = ShellSkill()
    
    async def execute(self, command: str, timeout: int = 30):
        """Execute shell command"""
        result = await self.skill._execute_command(command, timeout)
        return {
            "success": result[0].text.startswith("Exit code: 0") if result else False,
            "result": result[0].text if result else "",
            "error": None
        }
