import asyncio, json, os, sys
sys.path.insert(0, r'D:\AI-TTS\tools\mcp_lib')
sys.stdout.reconfigure(encoding='utf-8')
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

async def main():
    p = StdioServerParameters(command=r'D:\App\Conda\python.exe', args=['-I', r'D:\AI-TTS\studio\agent_mcp.py'], env={**os.environ, 'STUDIO_URL': 'http://127.0.0.1:' + os.environ.get('STUDIO_TEST_PORT', '7897') + ''})
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print('tools:', [t.name for t in tools.tools])
            for name, args in [('whoami', {}), ('list_videos', {'limit': 2}), ('job_status', {'jobs': sys.argv[1:]})]:
                res = await s.call_tool(name, args)
                txt = ''.join(getattr(c, 'text', '') for c in res.content)
                print(name, '->', txt[:600])
asyncio.run(main())
