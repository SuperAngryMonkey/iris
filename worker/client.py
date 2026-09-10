"""Minimal MCP client for iris-worker.

Usage:
  IRIS_URL=https://your-worker/mcp IRIS_BEARER=<token> python client.py __list__
  IRIS_URL=https://your-worker/mcp IRIS_BEARER=<token> python client.py iris_login
"""
import asyncio, os, sys
from mcp.client.streamable_http import streamablehttp_client
from mcp.client.session import ClientSession

URL = os.environ.get("IRIS_URL", "http://localhost:8787/mcp")
BEARER = os.environ.get("IRIS_BEARER", "")


async def main():
    tool = sys.argv[1] if len(sys.argv) > 1 else "__list__"
    headers = {"Authorization": f"Bearer {BEARER}"} if BEARER else {}
    async with streamablehttp_client(URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as s:
            await s.initialize()
            if tool == "__list__":
                r = await s.list_tools()
                print("TOOLS:", ", ".join(t.name for t in r.tools))
                return
            r = await s.call_tool(tool, {})
            for c in r.content:
                print(getattr(c, "text", c))


asyncio.run(main())
