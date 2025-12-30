
import os
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Dict, List

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.utils.settings import SETTINGS


class MCPClient:
    def __init__(self, server_file: str = "server.py"):
        path = Path(os.path.abspath(__file__))
        env = os.environ.copy()
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = f"{str(path.parents[2])}:{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = str(path.parents[2])

        current_dir = str(path.parents[0])
        server_path = os.path.join(current_dir, server_file)
        self.server_params = StdioServerParameters(
            command=SETTINGS.python_exe,
            args=[server_path],
            env=env,
        )
        self.exit_stack = AsyncExitStack()

    async def start_session(self):
        stdio_transport = await self.exit_stack.enter_async_context(stdio_client(self.server_params))
        self.stdio, self.write = stdio_transport
        self.session = await self.exit_stack.enter_async_context(ClientSession(self.stdio, self.write))
        await self.session.initialize()

    async def cleanup(self):
        if self.session:
            await self.exit_stack.aclose()

    async def call_tool(self, tool_name: str, tool_args: dict[str, any]):
        result = await self.session.call_tool(tool_name, tool_args)
        return result

    async def get_tools(self):
        response = await self.session.list_tools()
        return response.tools

    async def mcp_tools_to_openai(self, is_remote: bool, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        openai_tools: List[Dict[str, Any]] = []
        for t in tools:
            name = getattr(t, "name", None) or t.get("name")
            desc = getattr(t, "description", None) or t.get("description")
            schema = getattr(t, "inputSchema", None) or t.get("inputSchema")
            if not name or not schema:
                continue
            openai_tools.append(
                {
                    "name": name,
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": desc or "",
                        "parameters": schema,  # already JSON Schema per MCP
                    },
                    "is_remote": is_remote,
                }
            )
        return openai_tools
