"""
Shell Skill - MCP server for shell command execution.
"""
import asyncio
import structlog
from typing import Any
from mcp.server import Server
from mcp.types import Tool, TextContent

logger = structlog.get_logger()


class ShellSkill:
    """
    Shell execution skill for running commands.
    Implements MCP server interface with safety controls.
    """
    
    def __init__(
        self,
        allowed_commands: list[str] | None = None,
        blocked_commands: list[str] | None = None,
        max_output_size: int = 100000,
    ):
        self.allowed_commands = allowed_commands
        self.blocked_commands = blocked_commands or [
            "rm -rf /",
            "mkfs",
            "dd if=/dev/zero",
        ]
        self.max_output_size = max_output_size
        self.logger = logger.bind(component="ShellSkill")
        self.server = Server("shell-skill")
        
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="execute_command",
                    description="Execute a shell command",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Command to execute",
                            },
                            "timeout": {
                                "type": "integer",
                                "description": "Timeout in seconds (default: 30)",
                                "default": 30,
                            },
                            "working_dir": {
                                "type": "string",
                                "description": "Working directory (default: current)",
                            },
                        },
                        "required": ["command"],
                    },
                ),
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            self.logger.info("Tool called", tool=name, arguments=arguments)
            
            if name == "execute_command":
                return await self._execute_command(
                    arguments["command"],
                    arguments.get("timeout", 30),
                    arguments.get("working_dir"),
                )
            else:
                raise ValueError(f"Unknown tool: {name}")
    
    def _is_blocked(self, command: str) -> bool:
        """Check if command is in blocked list."""
        for blocked in self.blocked_commands:
            if blocked in command:
                return True
        return False
    
    async def _execute_command(
        self,
        command: str,
        timeout: int = 30,
        working_dir: str | None = None,
    ) -> list[TextContent]:
        """Execute a shell command."""
        try:
            # Safety check
            if self._is_blocked(command):
                return [TextContent(
                    type="text",
                    text=f"Error: Command blocked for safety: {command}"
                )]
            
            self.logger.info("Executing command", command=command, timeout=timeout)
            
            # Run command
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                process.kill()
                return [TextContent(
                    type="text",
                    text=f"Error: Command timed out after {timeout} seconds"
                )]
            
            # Format output
            output_parts = []
            
            if stdout:
                stdout_text = stdout.decode("utf-8", errors="replace")
                if len(stdout_text) > self.max_output_size:
                    stdout_text = stdout_text[:self.max_output_size] + "\n... (truncated)"
                output_parts.append(f"STDOUT:\n{stdout_text}")
            
            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if len(stderr_text) > self.max_output_size:
                    stderr_text = stderr_text[:self.max_output_size] + "\n... (truncated)"
                output_parts.append(f"STDERR:\n{stderr_text}")
            
            output_parts.append(f"Exit code: {process.returncode}")
            
            result = "\n\n".join(output_parts)
            return [TextContent(type="text", text=result)]
            
        except Exception as e:
            self.logger.error("Command execution failed", error=str(e))
            return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    def get_server(self) -> Server:
        """Get the MCP server instance."""
        return self.server


async def main():
    """Run the shell skill MCP server."""
    from mcp.server.stdio import stdio_server
    
    skill = ShellSkill()
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
