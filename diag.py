import sys
from playwright.sync_api import sync_playwright

url = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=False)
    page = b.new_context(no_viewport=True).new_page()
    hits = []
    page.on("request", lambda r: hits.append(r.url) if "chatbase" in r.url.lower() else None)
    page.goto(url, wait_until="load", timeout=45000)
    page.wait_for_timeout(15000)
    print("requests mentioning chatbase:", hits[:10] or "none")
    print("window.chatbase:", page.evaluate("typeof window.chatbase"))
    print("html mentions chatbase:", "chatbase" in page.content().lower())
    for f in page.frames:
        print("frame:", f.url[:110])
    b.close()
