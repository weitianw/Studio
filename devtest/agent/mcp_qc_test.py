import asyncio, os, sys
sys.path.insert(0, r'D:\AI-TTS\tools\mcp_lib')
sys.stdout.reconfigure(encoding='utf-8')
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
async def main():
    p = StdioServerParameters(command=r'D:\App\Conda\python.exe', args=['-I', r'D:\AI-TTS\studio\agent_mcp.py'], env={**os.environ, 'STUDIO_URL': 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897') + ''})
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for name, args in [('wait_jobs', {'jobs': [sys.argv[1]], 'timeout_min': 1}), ('check_quality', {'job': sys.argv[1]})]:
                res = await s.call_tool(name, args)
                print(name, '->', ''.join(getattr(c, 'text', '') for c in res.content)[:900])
asyncio.run(main())
