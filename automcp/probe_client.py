import os
import sys
import anyio
from pathlib import Path

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

SERVER_DIR = Path(__file__).parent.parent
SERVER_PATH = SERVER_DIR / "automcp.py"

DEFAULT_PATH = os.environ.get(
    "VERIFAI_ASSISTANT_DIR", r"C:\\Users\\silva\\AppData\\Roaming\\VerifAI Assistant"
)


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-u", str(SERVER_PATH), "--path", DEFAULT_PATH],
        cwd=str(SERVER_DIR),
        env=os.environ.copy(),
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = [t.name for t in tools.tools]
            print("tools:", tool_names)

            if "get_experts" not in tool_names:
                raise RuntimeError("get_experts não anunciado pelo servidor")

            result = await session.call_tool("get_experts", {})
            texts = [c.text for c in result.content if hasattr(c, "text")]
            print("result sample:\n", "\n".join(texts[:1]))


if __name__ == "__main__":
    anyio.run(main)
