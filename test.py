from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=False)
    ctx = browser.new_context(locale="de-DE", timezone_id="Europe/Berlin")
    page = ctx.new_page()
    page.on("request", lambda r: print(r.method, r.url))
    page.goto("https://example.com")
    page.wait_for_timeout(3000)
    browser.close()
