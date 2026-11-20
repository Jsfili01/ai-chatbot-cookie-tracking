"""Analyze capture files: cookie inventory + consent compliance + leak matching.

Usage:
  python analyze.py captures/*.json
Optional: put open-cookie-database.csv in this folder for cookie categories
Outputs (in ./analysis): cookies.csv, hits.csv, third_parties.csv
"""
import base64
import csv
import gzip
import json
import re
import sys
import zlib
from pathlib import Path
from urllib.parse import unquote, unquote_plus

import tldextract

from canaries import build_lookup, confidence

STAGES = ["1_load", "2_consent", "3_chat_open", "4_chat_sent"]
NON_ESSENTIAL = {"analytics", "marketing", "advertising"}

# Fallback guesses when a cookie isn't in the Open Cookie Database.
HEURISTICS = [
    ("analytics", r"^(_ga|_gid|_gat|_hj|ajs_|_pk_|mp_|_clck|_clsk|CLID|SM$|MR$|_dc_gtm)"),
    ("marketing", r"^(_fbp|_fbc|_gcl|IDE$|test_cookie|fr$|_uet|_ttp|_scid|MUID|li_|bcookie|lidc|_pin_|__qca|NID$|DSID|_rdt)"),
    ("functional", r"^(intercom-|drift|__stripe|_zendesk|__zlcmid|ada|tidio|hubspot|__hs|__cf|cf_|_cfuvid|JSESSIONID|PHPSESSID|csrf|XSRF)"),
    ("consent", r"(OptanonConsent|OptanonAlertBoxClosed|CookieConsent|euconsent|usprivacy|cookieyes|CookieScriptConsent|consent)"),
]


def load_cookie_db(path="open-cookie-database.csv"):
    exact, wild = {}, []
    if not Path(path).exists():
        return exact, wild
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = row["Cookie / Data Key name"]
            cat = row["Category"].strip().lower()
            if row["Wildcard match"].strip() == "1":
                wild.append((name, cat))
            else:
                exact.setdefault(name, cat)
    return exact, wild


EXACT, WILD = load_cookie_db()


def categorize(name):
    if name in EXACT:
        return EXACT[name], "open-cookie-db"
    for prefix, cat in WILD:
        if name.startswith(prefix):
            return cat, "open-cookie-db"
    for cat, rx in HEURISTICS:
        if re.search(rx, name):
            return cat, "heuristic"
    return "unknown", "-"


def reg_domain(host_or_url):
    ext = tldextract.extract(host_or_url)
    d = getattr(ext, "top_domain_under_public_suffix", None) or ext.registered_domain
    return d or ext.domain or host_or_url


def decompress(b):
    for fn in (gzip.decompress, zlib.decompress,
               lambda x: zlib.decompress(x, -15)):
        try:
            return fn(b)
        except Exception:
            pass
    return b


B64_RX = re.compile(r"[A-Za-z0-9+/_-]{16,}={0,2}")


def views(text):
    """Raw text plus URL-decoded and base64-decoded versions of it."""
    yield text
    yield unquote(text)
    yield unquote_plus(text)
    for tok in B64_RX.findall(text)[:50]:
        pad = tok + "=" * (-len(tok) % 4)
        for dec in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                out = decompress(dec(pad)).decode("utf-8", errors="ignore")
                if out.strip():
                    yield out
            except Exception:
                pass


def lifetime_days(c):
    exp = c.get("expires", -1)
    return "session" if exp in (-1, None) or exp < 0 else round(
        (exp - c.get("_t", 0)) / 86400, 1)


SITE_FIELDS = ["site", "country", "consent", "scenario", "run_id", "verdict",
               "reasons", "blocked", "block_reason", "banner_present",
               "no_reject_option", "consent_method", "consent_state_after",
               "widget_present_before", "widget_present_after",
               "widget_vendor"]


def verdict_for(d):
    """One verdict per run, from the observations capture.py recorded.
    BLOCKED / FAIL / INCONCLUSIVE / NO_WIDGET / PASS (LEGACY = old capture)."""
    if "banner_present" not in d:
        return "LEGACY", []
    if d.get("blocked"):
        return "BLOCKED", []
    arm = d.get("consent_mode")
    banner = d["banner_present"]
    before, after = d["widget_present_before"], d["widget_present_after"]
    reasons = []
    if before:
        reasons.append("widget_before_consent" if banner else "widget_no_banner")
    elif not banner and after:
        reasons.append("widget_no_banner")
    if d["no_reject_option"]:
        reasons.append("no_reject_option")
    if arm == "reject" and d["consent_state_after"] == "denied" and after:
        reasons.append("widget_after_reject")
    if reasons:
        return "FAIL", reasons
    if arm in ("accept", "reject") and banner \
            and d["consent_state_after"] == "unknown":
        return "INCONCLUSIVE", ["consent_state_unreadable"]
    if not banner and not after:
        return "NO_WIDGET", []
    if arm == "accept" and not before and not after:
        return "NO_WIDGET", []
    return "PASS", []


def normalize(d):
    """Accept both capture formats: old (snapshots dict, 'requests') and new
    (snapshots list with 'stage', 'requests_log')."""
    if isinstance(d.get("snapshots"), list):
        d["snapshots"] = {s["stage"]: s for s in d["snapshots"]}
    if "requests_log" in d and "requests" not in d:
        d["requests"] = d["requests_log"]
    return d


def analyze(path, lookup_cache, w_cookies, w_hits, w_tp, w_sites):
    d = normalize(json.load(open(path)))
    site = reg_domain(d["start_url"])
    meta = {"site": site, "country": d["country"],
            "consent": d["consent_mode"], "scenario": d["canaries"]["scenario"]}
    lookup = lookup_cache.setdefault(
        d["canaries"]["token"],
        {v: m for v, m in build_lookup(d["canaries"]).items()
         if not m[1].endswith(("adler32", "crc32")) and len(v) >= 6})

    verdict, reasons = verdict_for(d)
    w_sites.writerow({**meta, "run_id": d.get("run_id", ""),
                      "verdict": verdict, "reasons": ";".join(reasons),
                      "blocked": d.get("blocked", ""),
                      "block_reason": d.get("block_reason") or "",
                      "banner_present": d.get("banner_present", ""),
                      "no_reject_option": d.get("no_reject_option", ""),
                      "consent_method": d.get("consent_method") or "",
                      "consent_state_after": d.get("consent_state_after", ""),
                      "widget_present_before": d.get("widget_present_before", ""),
                      "widget_present_after": d.get("widget_present_after", ""),
                      "widget_vendor": d.get("widget_vendor") or ""})

    print("=" * 70)
    print(f"{site}  country={meta['country']}  consent={meta['consent']} "
          f"({d.get('consent_method')})  scenario={meta['scenario']}")
    print(f"VERDICT: {verdict}" + (f"  ({', '.join(reasons)})" if reasons else ""))

    # ---- cookies per stage ----------------------------------------------
    seen_prev, per_stage = set(), {}
    for stage in STAGES:
        snap = d["snapshots"].get(stage)
        if not snap:
            continue
        rows = []
        for c in snap["cookies"]:
            c["_t"] = snap["t"]
            cat, src = categorize(c["name"])
            key = (c["name"], c["domain"])
            row = {
                **meta, "stage": stage, "name": c["name"],
                "domain": c["domain"],
                "party": "first" if reg_domain(c["domain"].lstrip(".")) == site else "third",
                "category": cat, "category_source": src,
                "lifetime_days": lifetime_days(c), "secure": c["secure"],
                "httpOnly": c["httpOnly"], "sameSite": c.get("sameSite", ""),
                "new_this_stage": key not in seen_prev,
                "contains_canary": any(v in c["value"] for v in lookup),
            }
            rows.append(row)
            w_cookies.writerow(row)
        seen_prev |= {(r["name"], r["domain"]) for r in rows}
        per_stage[stage] = rows

    # ---- consent compliance summary --------------------------------------
    def ne(rows):
        return [r for r in rows if r["category"] in NON_ESSENTIAL]

    load = per_stage.get("1_load", [])
    print(f"\nCookies per stage (total / third-party / non-essential / unknown)")
    for s, rows in per_stage.items():
        print(f"  {s:12} {len(rows):3} / {sum(r['party']=='third' for r in rows):3} / "
              f"{len(ne(rows)):3} / {sum(r['category']=='unknown' for r in rows):3}"
              f"   new this stage: {sum(r['new_this_stage'] for r in rows)}")
    if ne(load):
        print(f"\n  ! Non-essential cookies set BEFORE any consent action:")
        for r in ne(load):
            print(f"      {r['name']:24} {r['domain']:26} {r['category']}")
    if meta["consent"] == "reject" and "2_consent" in per_stage:
        after = [r for r in ne(per_stage["2_consent"])]
        if after:
            print(f"  ! Non-essential cookies still present AFTER rejecting:")
            for r in after:
                print(f"      {r['name']:24} {r['domain']:26} "
                      f"{'(new)' if r['new_this_stage'] else '(pre-existing)'}")
    chat_new = [r for s in ("3_chat_open", "4_chat_sent")
                for r in per_stage.get(s, []) if r["new_this_stage"]]
    if chat_new:
        print(f"\n  Cookies created by opening/using the chat:")
        for r in chat_new:
            print(f"      {r['stage']:12} {r['name']:24} {r['domain']:26} "
                  f"{r['party']:5} {r['category']}")

    # ---- third parties by first-seen stage -------------------------------
    first_seen = {}
    for rec in d["requests"]:
        dom = reg_domain(rec["url"])
        if dom != site and dom not in first_seen:
            first_seen[dom] = rec["stage"]
    for dom, stage in sorted(first_seen.items(), key=lambda x: x[1]):
        w_tp.writerow({**meta, "domain": dom, "first_seen_stage": stage})
    by_stage = {}
    for dom, st in first_seen.items():
        by_stage.setdefault(st, []).append(dom)
    print(f"\nThird-party domains by stage first contacted:")
    for st in STAGES:
        doms = sorted(by_stage.get(st, []))
        if doms:
            print(f"  {st:12} {len(doms):3}  {', '.join(doms[:8])}"
                  f"{' ...' if len(doms) > 8 else ''}")

    # ---- leak matching ---------------------------------------------------
    hits = set()

    def search(text, stage, dom, where):
        party = "-" if dom.startswith("(") else ("first" if dom == site else "third")
        for view in views(text):
            for variant, (name, transform) in lookup.items():
                if variant in view:
                    hits.add((stage, dom, party, name, transform, where,
                              confidence(name)))

    for rec in d["requests"]:
        dom = reg_domain(rec["url"])
        search(rec["url"], rec["stage"], dom, "url")
        search(json.dumps(rec["headers"]), rec["stage"], dom, "headers")
        if rec["post_b64"]:
            body = decompress(base64.b64decode(rec["post_b64"]))
            search(body.decode("utf-8", errors="ignore"), rec["stage"], dom,
                   "body")
    for r in d["responses"]:
        if r["request_cookie_header"]:
            search(r["request_cookie_header"], r["stage"],
                   reg_domain(r["url"]), "cookie-header")
    for stage, snap in d["snapshots"].items():
        search(snap["title"], stage, "(page title)", "title")

    print(f"\nLeak matches: {len(hits)}")
    order = {"high": 0, "medium": 1, "low": 2}
    for h in sorted(hits, key=lambda h: (order[h[6]], h[0], h[1])):
        w_hits.writerow(dict(zip(
            ["stage", "domain", "party", "canary", "transform", "where",
             "confidence"], h), **meta))
        if h[6] != "low":
            print(f"  [{h[6]:6}] {h[0]:12} {h[2]:5} {h[1]:26} "
                  f"{h[3]:11} {h[4]:20} in {h[5]}")
    low = sum(h[6] == "low" for h in hits)
    if low:
        print(f"  (+{low} low-confidence keyword matches in hits.csv)")


def main(paths, out_dir="analysis"):
    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    meta_f = ["site", "country", "consent", "scenario"]
    with open(out / "cookies.csv", "w", newline="") as fc, \
         open(out / "hits.csv", "w", newline="") as fh, \
         open(out / "third_parties.csv", "w", newline="") as ft, \
         open(out / "sites.csv", "w", newline="") as fs:
        wc = csv.DictWriter(fc, meta_f + [
            "stage", "name", "domain", "party", "category", "category_source",
            "lifetime_days", "secure", "httpOnly", "sameSite",
            "new_this_stage", "contains_canary"])
        wh = csv.DictWriter(fh, meta_f + [
            "stage", "domain", "party", "canary", "transform", "where",
            "confidence"])
        wt = csv.DictWriter(ft, meta_f + ["domain", "first_seen_stage"])
        ws = csv.DictWriter(fs, SITE_FIELDS)
        for w in (wc, wh, wt, ws):
            w.writeheader()
        cache = {}
        for p in paths:
            analyze(p, cache, wc, wh, wt, ws)
    print(f"\nWrote {out}/sites.csv, cookies.csv, hits.csv, third_parties.csv")
    if not EXACT:
        print("Tip: add open-cookie-database.csv for better cookie labels.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    args = sys.argv[1:]
    out_dir = "analysis"
    if "--out" in args:
        i = args.index("--out")
        out_dir = args[i + 1]
        del args[i:i + 2]
    main(args, out_dir)
