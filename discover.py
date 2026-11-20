"""Find sites that really run a chat widget, and record the evidence.

Stage 1 (no browser, concurrent): fetch the HTML, look for a vendor script.
Stage 2 (Chrome, fresh profile per site): load the page and collect three
kinds of evidence, separately BEFORE consent and AFTER clicking Accept:
  - on-screen elements (DOM selectors from capture.py)
  - JavaScript globals (window.chatbase, window.Intercom, ...)
  - network hosts the page contacts (chatbase.co, impel.io, ...)
Any unrecognised chat-like host is also saved so new vendors can be spotted.

Usage:
  python discover.py sites.txt --db run1.db --out run1.csv --deep
"""
import argparse
import asyncio
import csv
import re
import sqlite3
import time
import urllib.robotparser
from urllib.parse import urlparse

import httpx

UA = "Mozilla/5.0 (compatible; widget-cookie-study/1.0; research crawler)"

# Stage 1: regex over page HTML.
SIGNATURES = {
    "canary": r"__CANARY_",
    "chatbase": r"chatbase\.co",
    "intercom": r"widget\.intercom\.io|js\.intercomcdn\.com",
    "drift": r"js\.driftt\.com|drift\.com/include",
    "ada": r"static\.ada\.support|cdn\.ada\.support",
    "tidio": r"code\.tidio\.co",
    "crisp": r"client\.crisp\.chat",
    "livechat": r"cdn\.livechatinc\.com",
    "zendesk": r"static\.zdassets\.com|ekr\.zdassets\.com",
    "hubspot": r"js\.usemessages\.com",
    "freshchat": r"wchat\.freshchat\.com",
    "gorgias": r"config\.gorgias\.chat|cdn\.gorgias\.com",
    "tawk": r"embed\.tawk\.to",
    "salesforce": r"service\.force\.com|embeddedservice",
    "liveperson": r"lptag\.liveperson\.net",
    "paradox": r"paradox\.ai",
    "impel": r"impel\.(io|ai)",
}
SIG_RX = {v: re.compile(rx, re.I) for v, rx in SIGNATURES.items()}

# Stage 2: hostnames the page contacts. Seen in your probe unless noted.
HOST_SIGNATURES = {
    "chatbase": r"(^|\.)chatbase\.co$",
    "impel": r"(^|\.)impel\.(io|ai)$",
    "liveperson": r"(^|\.)liveperson\.(net|com)$",
    "intercom": r"(^|\.)(intercom\.io|intercomcdn\.com)$",
    "zendesk": r"(^|\.)zdassets\.com$",
    "ada": r"(^|\.)ada\.support$",
    "drift": r"(^|\.)driftt\.com$",
    "tidio": r"(^|\.)tidio\.co$",
    "crisp": r"(^|\.)crisp\.chat$",
    "tawk": r"(^|\.)tawk\.to$",
    "freshchat": r"(^|\.)freshchat\.com$",
    "carnow": r"(^|\.)carnow\.com$",
    "letzchat": r"letzchat",
}
HOST_RX = {v: re.compile(rx, re.I) for v, rx in HOST_SIGNATURES.items()}
# loose catch-all, just to flag things for human review
CHATLIKE = re.compile(r"chat|webchat|assistant|livechat|helpdesk|messenger|"
                      r"convers|botpress|voiceflow|landbot", re.I)
GLOBALS = {"chatbase": "chatbase", "intercom": "Intercom", "drift": "drift",
           "zendesk": "zE", "crisp": "$crisp", "tawk": "Tawk_API",
           "ada": "adaSettings", "hubspot": "HubSpotConversations",
           "tidio": "tidioChatApi", "livechat": "LC_API",
           "freshchat": "FreshworksWidget", "olark": "olark"}

CMP_RX = re.compile(r"onetrust|cookiebot|usercentrics|didomi|quantcast|"
                    r"osano|klaro|complianz|trustarc|cookieyes", re.I)
_robots = {}


def host_vendor(hosts):
    """First known vendor whose host pattern matches any contacted host."""
    for vendor, rx in HOST_RX.items():
        if any(rx.search(h) for h in hosts if h):
            return vendor
    return ""


def www_variant(url):
    p = urlparse(url)
    if p.hostname and not p.hostname.startswith("www.") and p.hostname.count(".") == 1:
        return url.replace("//" + p.hostname, "//www." + p.hostname, 1)
    return None


def normalize(u):
    u = u.strip()
    if not u or u.startswith("#"):
        return None
    return u if re.match(r"^https?://", u) else "https://" + u


async def robots_ok(client, url):
    p = urlparse(url)
    origin = f"{p.scheme}://{p.netloc}"
    if origin not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = await client.get(origin + "/robots.txt")
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp.parse([])
        _robots[origin] = rp
    return _robots[origin].can_fetch(UA, url)


async def passive_one(client, sem, url):
    async with sem:
        row = {"url": url, "s1_status": "", "s1_vendor": "", "cmp": 0}
        try:
            if not await robots_ok(client, url):
                row["s1_status"] = "robots"
                return row
            r = await client.get(url)
        except Exception as e:
            row["s1_status"] = f"error:{type(e).__name__}"
            return row
        if r.status_code in (403, 429, 503):
            row["s1_status"] = f"blocked:{r.status_code}"
            return row
        if r.status_code >= 400:
            row["s1_status"] = f"http:{r.status_code}"
            return row
        html = r.text[:600_000]
        html = re.sub(r"<link\b[^>]*>", "", html, flags=re.I)  # ignore preconnect hints
        row["s1_status"] = "ok"
        row["cmp"] = int(bool(CMP_RX.search(html)))
        for vendor, rx in SIG_RX.items():
            if rx.search(html):
                row["s1_vendor"] = vendor
                break
        return row


async def run_passive(urls, concurrency):
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency)
    async with httpx.AsyncClient(headers={"User-Agent": UA}, timeout=15,
                                 follow_redirects=True, limits=limits) as c:
        tasks = [asyncio.create_task(passive_one(c, sem, u)) for u in urls]
        done = []
        for i, t in enumerate(asyncio.as_completed(tasks), 1):
            done.append(await t)
            if i % 100 == 0:
                print(f"  stage 1: {i}/{len(urls)}", flush=True)
        return done


NEW_COLS = {"net_vendor_before": "TEXT", "net_vendor_after": "TEXT",
            "global_vendor": "TEXT", "chat_hosts": "TEXT"}


def init_db(path):
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE IF NOT EXISTS results(
        url TEXT PRIMARY KEY, s1_status TEXT, s1_vendor TEXT, cmp INTEGER,
        s2_done INTEGER DEFAULT 0, s2_error TEXT, blocked INTEGER,
        banner_present INTEGER, widget_before INTEGER,
        widget_after_accept INTEGER, widget_vendor TEXT, ts REAL)""")
    for col, typ in NEW_COLS.items():
        try:
            db.execute(f"ALTER TABLE results ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass  # already there
    return db


def global_vendor(page):
    for vendor, g in GLOBALS.items():
        try:
            if page.evaluate(f"typeof window['{g}'] !== 'undefined'"):
                return vendor
        except Exception:
            pass
    return ""


def on_screen(page, detect_widget):
    found, vendor = detect_widget(page)
    return (vendor or "") if found else ""


def confirm(browser, url, wait_s, widget_wait):
    from capture import (banner_dialog_visible, detect_block, detect_widget,
                         find_consent_control, try_consent)
    ctx = browser.new_context(no_viewport=True)
    page = ctx.new_page()
    hosts = set()
    page.on("request", lambda rq: hosts.add(urlparse(rq.url).hostname or ""))
    try:
        resp = page.goto(url, wait_until="load", timeout=45_000)  # ms!
        page.wait_for_timeout(wait_s * 1000)
        status = resp.status if resp else None
        headers = {k.lower(): v for k, v in
                   (resp.headers.items() if resp else [])}
        blocked, why = detect_block(page, status, headers)
        if blocked:
            return {"blocked": 1, "why": why, "banner": 0, "before": 0,
                    "after": 0, "vendor": "", "nb": "", "na": "", "gv": "",
                    "chat": ""}
        a, _ = find_consent_control(page, "accept")
        r, _ = find_consent_control(page, "reject")
        banner = int(a is not None or r is not None
                     or banner_dialog_visible(page))

        # ---- BEFORE consent ----
        for _ in range(int(widget_wait * 2)):          # poll for late widgets
            dom = on_screen(page, detect_widget)
            gv = global_vendor(page)
            if dom or gv:
                break
            page.wait_for_timeout(500)
        net_before = host_vendor(hosts)
        before = int(bool(dom or gv))
        vendor = dom or gv

        # ---- AFTER Accept (only if a banner could be hiding it) ----
        after, net_after = 0, ""
        if not before and banner and try_consent(page, "accept"):
            for _ in range(int(widget_wait * 2)):
                dom = on_screen(page, detect_widget)
                gv = global_vendor(page)
                if dom or gv:
                    break
                page.wait_for_timeout(500)
            after = int(bool(dom or gv))
            vendor = dom or gv or vendor
            net_after = host_vendor(hosts)
        chat = sorted(h for h in hosts if h and CHATLIKE.search(h))
        return {"blocked": 0, "why": "", "banner": banner, "before": before,
                "after": after, "vendor": vendor, "nb": net_before,
                "na": net_after, "gv": gv or "", "chat": ";".join(chat[:8])}
    finally:
        ctx.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("--db", default="discover.db")
    ap.add_argument("--out", default="queue.csv")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--passive-only", action="store_true")
    ap.add_argument("--deep", action="store_true")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--wait", type=int, default=5)
    ap.add_argument("--widget-wait", type=int, default=10)
    a = ap.parse_args()

    urls = [u for u in (normalize(x) for x in open(a.candidates)) if u]
    if a.limit:
        urls = urls[:a.limit]
    db = init_db(a.db)
    known = {r[0] for r in db.execute("SELECT url FROM results")}
    todo = [u for u in urls if u not in known]
    print(f"{len(urls)} candidates, {len(known & set(urls))} already done, "
          f"{len(todo)} new")

    if todo:
        t0 = time.time()
        for row in asyncio.run(run_passive(todo, a.concurrency)):
            db.execute("INSERT OR IGNORE INTO results(url,s1_status,s1_vendor,"
                       "cmp,ts) VALUES(?,?,?,?,?)",
                       (row["url"], row["s1_status"], row["s1_vendor"],
                        row["cmp"], time.time()))
        db.commit()
        print(f"stage 1 done in {time.time()-t0:.0f}s")

    if not a.passive_only:
        cond = "s1_status='ok'" + ("" if a.deep else " AND s1_vendor!=''")
        q = ("SELECT url FROM results WHERE s2_done=0 AND ((" + cond +
             ") OR s1_status LIKE 'blocked:%' OR s1_status LIKE 'error:%')")
        wanted = set(urls)
        targets = [r[0] for r in db.execute(q) if r[0] in wanted]
        print(f"stage 2 (browser) on {len(targets)} sites")
        if targets:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome",
                                            headless=a.headless)
                for i, url in enumerate(targets, 1):
                    try:
                        try:
                            r = confirm(browser, url, a.wait, a.widget_wait)
                        except Exception:
                            alt = www_variant(url)
                            if not alt:
                                raise
                            r = confirm(browser, alt, a.wait, a.widget_wait)
                        db.execute(
                            "UPDATE results SET s2_done=1, blocked=?, "
                            "banner_present=?, widget_before=?, "
                            "widget_after_accept=?, widget_vendor=?, "
                            "s2_error=?, net_vendor_before=?, "
                            "net_vendor_after=?, global_vendor=?, "
                            "chat_hosts=? WHERE url=?",
                            (r["blocked"], r["banner"], r["before"],
                             r["after"], r["vendor"], r["why"], r["nb"],
                             r["na"], r["gv"], r["chat"], url))
                        tag = ("BLOCKED" if r["blocked"] else
                               f"screen={r['before']}/{r['after']} "
                               f"net={r['nb'] or r['na'] or '-'}")
                        print(f"[{i}/{len(targets)}] {tag:34} "
                              f"{(r['vendor'] or ''):10} {url}", flush=True)
                    except Exception as e:
                        db.execute("UPDATE results SET s2_done=1, s2_error=? "
                                   "WHERE url=?",
                                   (f"{type(e).__name__}: {str(e)[:100]}", url))
                        print(f"[{i}/{len(targets)}] ERROR {url}: "
                              f"{type(e).__name__}", flush=True)
                    db.commit()
                browser.close()

    rows = db.execute(
        "SELECT url, s1_vendor, widget_vendor, net_vendor_before, "
        "net_vendor_after, banner_present, widget_before, "
        "widget_after_accept, blocked, s1_status, chat_hosts, s2_error "
        "FROM results").fetchall()
    with open(a.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["url", "script_vendor", "widget_vendor",
                    "net_vendor_before_consent", "net_vendor_after_accept",
                    "banner_present", "on_screen_before", "on_screen_after",
                    "blocked", "stage1_status", "chat_like_hosts", "note"])
        for r in rows:
            if r[1] or r[2] or r[3] or r[4] or r[6] or r[7] or r[10]:
                w.writerow(r)
    ev = [r for r in rows if r[2] or r[3] or r[4] or r[6] or r[7]]
    print(f"\nwrote {a.out}: {len(ev)} sites with widget evidence "
          f"(on screen or vendor network traffic), "
          f"{sum(1 for r in rows if r[8])} blocked, "
          f"{sum(1 for r in rows if r[10] and not (r[2] or r[3] or r[4]))} "
          f"with only unrecognised chat-like hosts (review by hand)")


if __name__ == "__main__":
    main()
