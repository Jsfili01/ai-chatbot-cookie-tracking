"""Staged capture of one site under one country / consent condition.

Stages (cookies are snapshotted after each one):
  1_load       page loaded, banner untouched
  2_consent    banner accepted / rejected / ignored
  3_chat_open  chat widget opened, nothing typed
  4_chat_sent  scenario message sent, reply received

Usage:
  python capture.py https://example.com --country DE --consent reject
  python capture.py https://example.com --scenario order_support --consent accept
  python capture.py --selftest
"""
import argparse
import base64
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from playwright.sync_api import sync_playwright

from canaries import SCENARIOS, make_canaries

COUNTRIES = {  # locale, timezone, (lat, lon)
    "US": ("en-US", "America/New_York", (40.7128, -74.0060)),
    "GB": ("en-GB", "Europe/London", (51.5074, -0.1278)),
    "DE": ("de-DE", "Europe/Berlin", (52.5200, 13.4050)),
    "FR": ("fr-FR", "Europe/Paris", (48.8566, 2.3522)),
    "BR": ("pt-BR", "America/Sao_Paulo", (-23.5505, -46.6333)),
    "IN": ("en-IN", "Asia/Kolkata", (28.6139, 77.2090)),
    "JP": ("ja-JP", "Asia/Tokyo", (35.6762, 139.6503)),
    "AU": ("en-AU", "Australia/Sydney", (-33.8688, 151.2093)),
}

# Known consent-platform buttons (best effort; banners vary a lot)
ACCEPT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "#CybotCookiebotDialogBodyButtonAccept",
    "button[data-testid='uc-accept-all-button']",
    "#truste-consent-button",
]
REJECT_SELECTORS = [
    "#onetrust-reject-all-handler",
    "#CybotCookiebotDialogBodyButtonDecline",
    "button[data-testid='uc-deny-all-button']",
    "#truste-consent-required",
]
ACCEPT_RX = re.compile(
    r"^\s*(accept( all)?( cookies)?|allow all( cookies)?|agree|i agree|"
    r"got it|ok|okay|"
    r"alle akzeptieren|akzeptieren|alle zulassen|zustimmen|"          # de
    r"tout accepter|accepter( tout)?|"                                # fr
    r"aceptar( todo)?|aceitar( tudo)?|accetta( tutto)?)\s*$", re.I)
REJECT_RX = re.compile(
    r"^\s*(reject( all)?( cookies)?|decline( all)?|deny( all)?|"
    r"only necessary|necessary only|essential only|refuse( all)?|"
    r"alle ablehnen|ablehnen|nur notwendige|nur erforderliche|"       # de
    r"tout refuser|refuser( tout)?|continuer sans accepter|"          # fr
    r"rechazar( todo)?|rejeitar( tudo)?|rifiuta( tutto)?)\s*$", re.I)

# Anything that can plausibly be a consent button, including <img role=button>.
CONTROL_SEL = ("button, a, [role=button], input[type=button], "
               "input[type=submit], img[role=button]")
DIALOG_SEL = ("[role=dialog], [role=alertdialog], [id*=cookie i], "
              "[class*=cookie i], [id*=consent i], [class*=consent i], "
              "[aria-label*=cookie i], [aria-label*=consent i]")
DIALOG_TEXT_RX = re.compile(r"cookie|consent|datenschutz", re.I)

# Chat-widget fingerprints. Only "canary" is verified (by the canary pages);
# the vendor selectors are best-effort and should be checked on real sites.
WIDGETS = {
    "canary": "#canary-launcher, iframe#canary-frame",
    "chatbase": "#chatbase-bubble-button",
    "impel": '#impel-chatbot button[aria-label="chat-entry"]',
	"bestbuy": 'button[data-testid="dmn-ask-blue-icon-url"]',
    "intercom": ("#intercom-container, .intercom-lightweight-app, "
                 "iframe[name='intercom-launcher-frame'], iframe#intercom-frame"),
    "drift": "#drift-frame-controller, #drift-widget",
    "zendesk": "iframe#launcher, #ze-snippet",
    "tidio": "#tidio-chat, #tidio-chat-iframe",
    "crisp": ".crisp-client, #crisp-chatbox",
    "hubspot": "#hubspot-messages-iframe-container",
    "livechat": "#chat-widget-container, #livechat-compact-container",
    "freshchat": "#fc_frame, #freshworks-container",
    "ada": "#ada-button-frame",
    "gorgias": "#gorgias-chat-container",
    "tawk": ".tawk-min-container, iframe[title*='chat widget' i]",
    "salesforce": ".embeddedServiceHelpButton, #embeddedMessagingFrame",
}

BLOCK_MARKERS = re.compile(
    r"cf-browser-verification|challenge-running|Just a moment\.\.\.|"
    r"px-captcha|Attention Required! \| Cloudflare|_Incapsula_Resource|"
    r"Access Denied", re.I)


def _labels(loc):
    """text / aria-label / alt / title / value of every element in loc."""
    return loc.evaluate_all(
        """els => els.map(e => [
            (e.innerText || e.textContent || '').trim(),
            e.getAttribute('aria-label') || '', e.getAttribute('alt') || '',
            e.getAttribute('title') || '', e.value || ''])""")


def find_consent_control(page, mode):
    """First visible accept/reject control as (locator, method) or (None, None).
    Known CMP selectors first, then label matching in every frame. Playwright's
    CSS engine pierces open shadow roots, so shadow-DOM banners are covered."""
    sels, rx = ((ACCEPT_SELECTORS, ACCEPT_RX) if mode == "accept"
                else (REJECT_SELECTORS, REJECT_RX))
    for frame in page.frames:
        for sel in sels:
            try:
                loc = frame.locator(sel).first
                if loc.count() and loc.is_visible():
                    return loc, f"selector:{sel}"
            except Exception:
                pass
    for frame in page.frames:
        try:
            loc = frame.locator(CONTROL_SEL)
            for i, parts in enumerate(_labels(loc)):
                if any(rx.match(t) for t in parts if t):
                    el = loc.nth(i)
                    if el.is_visible():
                        return el, "label-match"
        except Exception:
            pass
    return None, None


def try_consent(page, mode):
    loc, method = find_consent_control(page, mode)
    if loc is None:
        return None
    try:
        loc.click(timeout=3000)
        return method
    except Exception:
        return None


def banner_dialog_visible(page):
    """Fallback banner check: a visible dialog-ish element that talks cookies."""
    for frame in page.frames:
        try:
            loc = frame.locator(DIALOG_SEL)
            for i in range(min(loc.count(), 20)):
                el = loc.nth(i)
                if el.is_visible() and DIALOG_TEXT_RX.search(
                        el.inner_text(timeout=500)):
                    return True
        except Exception:
            pass
    return False


def detect_widget(page):
    for name, sel in WIDGETS.items():
        for frame in page.frames:
            try:
                loc = frame.locator(sel)
                for i in range(min(loc.count(), 10)):
                    if loc.nth(i).is_visible():
                        return True, name
            except Exception:
                pass
    return False, None


def wait_for_widget(page, timeout_s):
    """Poll for a widget instead of sleeping a fixed time (slow widgets)."""
    waited = 0.0
    while True:
        found, vendor = detect_widget(page)
        if found or waited >= timeout_s:
            return found, vendor
        page.wait_for_timeout(500)
        waited += 0.5


def detect_block(page, status, headers):
    """(blocked, reason) from the main document response + page content."""
    if headers.get("cf-mitigated") == "challenge":
        return True, "cf-mitigated"
    if status in (403, 429, 503):
        return True, f"http-{status}"
    try:
        html = page.content()[:40000]
        m = BLOCK_MARKERS.search(html)
        if m and len(page.inner_text("body")) < 800:
            return True, f"marker:{m.group(0)}"
    except Exception:
        pass
    return False, None


def read_consent_state(cookies):
    """granted / denied / unknown, from the site's own consent cookie."""
    for c in cookies:
        n, v = c["name"], c["value"]
        if n == "cookieyes-consent":
            fields = dict(
                part.split(":", 1)
                for part in v.split(",")
                if ":" in part
            )

            if fields.get("action") == "yes":
                if fields.get("consent") == "yes":
                    return "granted"
                if fields.get("consent") == "no":
                    return "denied"
        if n == "canary_consent":
            return v if v in ("granted", "denied") else "unknown"
        if n == "OptanonConsent":  # groups=C0001:1,C0002:0,...
            m = re.search(r"groups=([^&]+)", unquote(v))
            if m:
                on = {g.split(":")[0] for g in m.group(1).split(",")
                      if g.endswith(":1")}
                return ("granted" if on & {"C0002", "C0003", "C0004"}
                        else "denied")
        if n == "CookieConsent":  # Cookiebot
            if re.search(r"(marketing|statistics)\s*:\s*true", v):
                return "granted"
            if re.search(r"(marketing|statistics)\s*:\s*false", v):
                return "denied"
    return "unknown"


def run(url, scenario, country, consent, proxy, out_dir, wait_s, auto,
        canaries=None, widget_wait=10):
    canaries = canaries or make_canaries(scenario)
    locale, tz, (lat, lon) = COUNTRIES[country]
    requests_log, responses_log, snapshots = [], [], {}
    state = {"stage": "1_load"}
    consent_method = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome", headless=False,
            proxy={"server": proxy} if proxy else None)
        ctx = browser.new_context(
            locale=locale, timezone_id=tz, no_viewport=True,
            geolocation={"latitude": lat, "longitude": lon})
        page = ctx.new_page()

        def on_request(r):
            try:
                buf = r.post_data_buffer
            except Exception:
                buf = None
            requests_log.append({
                "t": time.time(), "stage": state["stage"], "url": r.url,
                "method": r.method, "resource": r.resource_type,
                "headers": r.headers,
                "post_b64": base64.b64encode(buf).decode() if buf else None,
            })

        def on_response(resp):
            try:
                set_cookies = [h["value"] for h in resp.headers_array()
                               if h["name"].lower() == "set-cookie"]
                sent = resp.request.all_headers().get("cookie", "")
            except Exception:
                set_cookies, sent = [], ""
            responses_log.append({
                "t": time.time(), "stage": state["stage"], "url": resp.url,
                "status": resp.status, "set_cookie": set_cookies,
                "request_cookie_header": sent,
            })

        page.on("request", on_request)
        page.on("response", on_response)

        def snap(stage):
            snapshots[stage] = {
                "t": time.time(), "url": page.url, "title": page.title(),
                "cookies": ctx.cookies(),
            }
            print(f"  [{stage}] {len(snapshots[stage]['cookies'])} cookies, "
                  f"{len(requests_log)} requests so far")

        def pause(msg):
            if not auto:
                input(f"\n>>> {msg}\n    Press Enter here when done... ")

        # 1 ---- load
        print(f"Loading {url}  ({country}, consent={consent}, {scenario})")
        resp = page.goto(url, wait_until="load")
        page.wait_for_timeout(wait_s * 1000)
        snap("1_load")

        # ground-truth observations, taken BEFORE any consent click
        main_status = resp.status if resp else None
        main_headers = {k.lower(): v for k, v in
                        (resp.headers.items() if resp else [])}
        blocked, block_reason = detect_block(page, main_status, main_headers)
        banner_present = no_reject_option = False
        widget_before, widget_vendor = False, None
        if not blocked:
            accept_loc, _ = find_consent_control(page, "accept")
            reject_loc, _ = find_consent_control(page, "reject")
            banner_present = (accept_loc is not None or reject_loc is not None
                              or banner_dialog_visible(page))
            no_reject_option = banner_present and reject_loc is None
            widget_before, widget_vendor = detect_widget(page)

        # 2 ---- consent
        state["stage"] = "2_consent"
        if consent in ("accept", "reject") and not blocked:
            consent_method = try_consent(page, consent)
            if consent_method is None:
                if auto:
                    consent_method = "not_found"
                else:
                    pause(f"Couldn't find the banner automatically. "
                          f"Click '{consent}' yourself in the browser (or "
                          f"skip if there is no banner).")
                    consent_method = "manual"
        page.wait_for_timeout(wait_s * 1000)
        snap("2_consent")

        # did consent register, and did a widget show up? (condition-wait,
        # so slow widgets are not missed)
        consent_state_after = ("not_attempted" if consent == "none" or blocked
                               else read_consent_state(
                                   snapshots["2_consent"]["cookies"]))
        widget_after = False
        if not blocked:
            widget_after, v = wait_for_widget(page, widget_wait)
            widget_vendor = v or widget_vendor

        # 3 ---- chat open
        state["stage"] = "3_chat_open"
        pause("Open the chat widget (don't type anything yet).")
        page.wait_for_timeout(wait_s * 1000)
        snap("3_chat_open")

        # 4 ---- chat sent
        state["stage"] = "4_chat_sent"
        if not auto:
            print(f"\nMessage to send:\n  {canaries['prompt']}")
            input("\n>>> Click inside the chat's text box, then press Enter "
                  "here and I'll type the message... ")
            page.keyboard.type(canaries["prompt"], delay=30)
            page.keyboard.press("Enter")
            print("    Sent. Waiting for the reply (do NOT submit anything "
                  "else, no resume uploads).")
            page.wait_for_timeout(wait_s * 2000)
            pause("Wait until the bot has replied.")
        snap("4_chat_sent")

        browser.close()

    result = {
        "start_url": url, "country": country, "locale": locale,
        "timezone": tz, "proxy_used": bool(proxy), "consent_mode": consent,
        "consent_method": consent_method, "canaries": canaries,
        "schema_version": 2, "run_id": canaries["token"],
        "main_status": main_status, "blocked": blocked,
    # Web server and infrastructure information
    "main_response_headers": main_headers,
    "observed_server": main_headers.get("server", "unknown"),
    "powered_by": main_headers.get("x-powered-by", "unknown"),
    "via": main_headers.get("via", "unknown"),
    "cf_ray": main_headers.get("cf-ray"),
        "block_reason": block_reason,
        "banner_present": banner_present,
        "no_reject_option": no_reject_option,
        "consent_state_after": consent_state_after,
        "widget_present_before": widget_before,
        "widget_present_after": widget_after,
        "widget_vendor": widget_vendor,
        "snapshots": [{"stage": k, **v} for k, v in snapshots.items()],
        "requests_log": requests_log,
        "responses": responses_log,
    }
    Path(out_dir).mkdir(exist_ok=True)
    host = urlparse(url).netloc.replace(":", "_")
    path = Path(out_dir) / f"{host}_{country}_{consent}_{scenario}_{canaries['token']}.json"
    path.write_text(json.dumps(result, indent=2))
    print(f"\nSaved {len(requests_log)} requests, {len(responses_log)} "
          f"responses -> {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--url", dest="url_opt",
                    help="same as the positional URL (used by canary/selftest.py)")
    ap.add_argument("--scenario", default="careers", choices=SCENARIOS)
    ap.add_argument("--country", default="US", choices=COUNTRIES)
    ap.add_argument("--consent", default="none",
                    choices=["none", "accept", "reject"])
    ap.add_argument("--proxy", help="e.g. http://user:pass@host:port "
                    "(exit node should match --country)")
    ap.add_argument("--out", default="captures")
    ap.add_argument("--wait", type=int, default=5, help="seconds per stage")
    ap.add_argument("--widget-wait", type=int, default=10,
                    help="max extra seconds to wait for a chat widget "
                         "after consent")
    ap.add_argument("--auto", action="store_true",
                    help="no manual steps (skips the chat stages)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    a.url = a.url_opt or a.url

    if a.selftest:
        # plant canaries in the URL so the analyzer has something to find
        c = make_canaries(a.scenario)
        e = c["values"]["email"]
        a.url = (f"https://example.com/?email={quote(e)}"
                 f"&h={hashlib.sha256(e.encode()).hexdigest()}")
        a.auto = True
        selftest_canaries = c
    else:
        selftest_canaries = None
    if not a.url:
        ap.error("give a URL or use --selftest")
    run(a.url, a.scenario, a.country, a.consent, a.proxy, a.out, a.wait,
        a.auto, selftest_canaries, widget_wait=a.widget_wait)
