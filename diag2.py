"""Vendor-agnostic probe: what chat-like things does each page actually load?
Usage: python diag2.py candidates_chatbase.txt 10"""
import re
import sys
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

KW = re.compile(r"chat|bot|widget|assist|messag|convers|helpdesk|impel|podium|drift|"
                r"intercom|zendesk|zdassets|tidio|crisp|tawk|hubspot|liveperson|"
                r"freshchat|gorgias|botpress|voiceflow|landbot|manychat|ada\.", re.I)
GLOBALS = ["chatbase", "Intercom", "drift", "zE", "$crisp", "Tawk_API", "adaSettings",
           "HubSpotConversations", "tidioChatApi", "LC_API", "FreshworksWidget", "olark"]

urls = [u.strip() for u in open(sys.argv[1]) if u.strip()][: int(sys.argv[2])]
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=False)
    for url in urls:
        ctx = b.new_context(no_viewport=True)
        page = ctx.new_page()
        hosts = set()
        page.on("request", lambda r: hosts.add(urlparse(r.url).hostname or ""))
        try:
            page.goto(url, wait_until="load", timeout=45000)
            page.wait_for_timeout(12000)
            gl = [g for g in GLOBALS if page.evaluate(f"typeof window['{g}'] !== 'undefined'")]
            frames = [f.url[:90] for f in page.frames if KW.search(f.url)]
            print(f"\n== {url}")
            print("  chat-like hosts :", sorted(h for h in hosts if KW.search(h)) or "none")
            print("  chat-like frames:", frames or "none")
            print("  JS globals      :", gl or "none")
        except Exception as e:
            print(f"\n== {url}\n  ERROR {type(e).__name__}")
        ctx.close()
    b.close()
