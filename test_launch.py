import asyncio
from playwright.async_api import async_playwright
from modules.publishers.youtube.publisher import _launch_persistent_context
from pathlib import Path

async def main():
    async with async_playwright() as p:
        ctx, proc = _launch_persistent_context(p, "/tmp/yt-test", False)
        print("Pages:", len(ctx.pages))
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        print("Success!")
        await ctx.close()

asyncio.run(main())
