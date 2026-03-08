"""
File System Skill - MCP server for file system operations.
"""
import os
import structlog
from pathlib import Path
from typing import Any
from mcp.server import Server
from mcp.types import Tool, TextContent

logger = structlog.get_logger()


class FileSystemSkill:
    """
    File system skill providing read, write, and list operations.
    Implements MCP server interface.
    """
    
    def __init__(self, allowed_paths: list[str] | None = None):
        self.allowed_paths = allowed_paths or [os.getcwd()]
        self.logger = logger.bind(component="FileSystemSkill")
        self.server = Server("fs-skill")
        
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="read_file",
                    description="Read the contents of a file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file",
                            }
                        },
                        "required": ["path"],
                    },
                ),
                Tool(
                    name="write_file",
                    description="Write content to a file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the file",
                            },
                            "content": {
                                "type": "string",
                                "description": "Content to write",
                            },
                        },
                        "required": ["path", "content"],
                    },
                ),
                Tool(
                    name="list_directory",
                    description="List contents of a directory",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to the directory",
                            }
                        },
                        "required": ["path"],
                    },
                ),
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            self.logger.info("Tool called", tool=name, arguments=arguments)
            
            if name == "read_file":
                return await self._read_file(arguments["path"])
            elif name == "write_file":
                return await self._write_file(arguments["path"], arguments["content"])
            elif name == "list_directory":
                return await self._list_directory(arguments["path"])
            else:
                raise ValueError(f"Unknown tool: {name}")
    
    def _validate_path(self, path: str) -> Path:
        """Validate that path is within allowed directories."""
        target = Path(path).resolve()
        
        for allowed in self.allowed_paths:
            allowed_path = Path(allowed).resolve()
            if str(target).startswith(str(allowed_path)):
                return target
        
        raise PermissionError(f"Path {path} is not within allowed directories")
    
    async def _read_file(self, path: str) -> list[TextContent]:
        """Read a file."""
        try:
            target = self._validate_path(path)
            
            if not target.exists():
                return [TextContent(type="text", text=f"Error: File not found: {path}")]
            
            if not target.is_file():
                return [TextContent(type="text", text=f"Error: {path} is not a file")]
            
            content = target.read_text(encoding="utf-8")
            return [TextContent(type="text", text=content)]
            
        except PermissionError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error reading file: {str(e)}")]
    
    async def _write_file(self, path: str, content: str) -> list[TextContent]:
        """Write to a file."""
        try:
            target = self._validate_path(path)
            
            # Create parent directories if needed
            target.parent.mkdir(parents=True, exist_ok=True)
            
            target.write_text(content, encoding="utf-8")
            return [TextContent(type="text", text=f"Successfully wrote to {path}")]
            
        except PermissionError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error writing file: {str(e)}")]
    
    async def _list_directory(self, path: str) -> list[TextContent]:
        """List directory contents."""
        try:
            target = self._validate_path(path)
            
            if not target.exists():
                return [TextContent(type="text", text=f"Error: Directory not found: {path}")]
            
            if not target.is_dir():
                return [TextContent(type="text", text=f"Error: {path} is not a directory")]
            
            entries = []
            for item in target.iterdir():
                entry_type = "📁" if item.is_dir() else "📄"
                entries.append(f"{entry_type} {item.name}")
            
            result = f"Contents of {path}:\n" + "\n".join(entries)
            return [TextContent(type="text", text=result)]
            
        except PermissionError as e:
            return [TextContent(type="text", text=f"Error: {str(e)}")]
        except Exception as e:
            return [TextContent(type="text", text=f"Error listing directory: {str(e)}")]
    
    def get_server(self) -> Server:
        """Get the MCP server instance."""
        return self.server


async def main():
    """Run the file system skill MCP server."""
    import asyncio
    from mcp.server.stdio import stdio_server
    
    skill = FileSystemSkill()
    server = skill.get_server()
    
    async with stdio_server(server) as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
