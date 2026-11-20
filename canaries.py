"""Canary generation: unique dummy identity + scenario prompt, plus every
encoded/hashed variant (modelled on the matching procedure in the paper)."""
import base64
import gzip
import hashlib
import secrets
import zlib
from urllib.parse import quote, quote_plus

from Crypto.Hash import RIPEMD160  # pycryptodome

# Each scenario = a believable reason to talk to a site's chat widget.
# NEVER submit a real application or upload anything. Chat only.
SCENARIOS = {
    "careers": {
        "template": ("Hi, I'm {full_name}. I'd like to apply for the {role} "
                     "position. You can reach me at {email} or {phone_fmt}. "
                     "What are the next steps?"),
        "keywords": {"keyword_role": "Marketing Analyst"},
    },
    "order_support": {
        "template": ("Hi, I'm {full_name}. Where is my order {order_id}? "
                     "My email is {email}."),
        "keywords": {},
    },
    "general": {
        "template": ("Hi, I'm {full_name} ({email}). How can I contact "
                     "someone about my account?"),
        "keywords": {},
    },
    # replicates the paper's sensitive-prompt condition, for comparison
    "sensitive_query": {
        "template": "pregnancy test near me",
        "keywords": {"keyword_topic": "pregnancy"},
    },
}

# How much a match can be trusted:
#   high   = value contains this run's random token, so it can't be a coincidence
#   medium = fake phone number (only 100 possible values)
#   low    = ordinary words that sites may legitimately contain
HIGH = {"email", "first_name", "last_name", "full_name", "order_id", "prompt"}
MEDIUM = {"phone", "phone_fmt"}


def confidence(name):
    if name in HIGH:
        return "high"
    if name in MEDIUM:
        return "medium"
    return "low"


def make_canaries(scenario="careers", run_id=None):
    token = run_id or secrets.token_hex(3)
    last4 = 100 + secrets.randbelow(100)  # 555-01xx = reserved fictional range
    fields = {
        "first_name": f"Jane{token}",
        "last_name": f"Doe{token}",
        "full_name": f"Jane{token} Doe{token}",
        "email": f"jane.{token}@example.com",
        "phone": f"415555{last4:04d}",
        "phone_fmt": f"415-555-{last4:04d}",
        "order_id": f"ORD{token.upper()}",
        "role": "Marketing Analyst",
    }
    sc = SCENARIOS[scenario]
    prompt = sc["template"].format(**fields)
    values = {k: v for k, v in fields.items() if k != "role"}
    values.update(sc["keywords"])
    values["prompt"] = prompt
    return {"scenario": scenario, "token": token, "prompt": prompt,
            "values": values}


def _hashes(data: bytes):
    out = {}
    for name in ("md5", "sha1", "sha224", "sha256", "sha384", "sha512",
                 "sha3_224", "sha3_256", "sha3_384", "sha3_512"):
        out[name] = hashlib.new(name, data).hexdigest()
    r = RIPEMD160.new()
    r.update(data)
    out["ripemd160"] = r.hexdigest()
    return out


def _encodings(data: bytes, text: str):
    return {
        "hex": data.hex(),
        "base32": base64.b32encode(data).decode(),
        "base64": base64.b64encode(data).decode(),
        "base64url": base64.urlsafe_b64encode(data).decode().rstrip("="),
        "url": quote(text, safe=""),
        "url_plus": quote_plus(text),
        "gzip_b64": base64.b64encode(gzip.compress(data, mtime=0)).decode(),
        "deflate_b64": base64.b64encode(zlib.compress(data)).decode(),
        "adler32": format(zlib.adler32(data), "08x"),
        "crc32": format(zlib.crc32(data), "08x"),
    }


def build_lookup(canaries):
    """{variant_string: (canary_name, transform)}"""
    lookup = {}
    for name, value in canaries["values"].items():
        for label, cv in (("orig", value), ("lower", value.lower()),
                          ("upper", value.upper())):
            data = cv.encode()
            lookup.setdefault(cv, (name, f"plain/{label}"))
            for t, v in _encodings(data, cv).items():
                lookup.setdefault(v, (name, f"{label}/{t}"))
            for t, v in _hashes(data).items():
                lookup.setdefault(v, (name, f"{label}/{t}"))
    return lookup


if __name__ == "__main__":
    import json
    import sys
    sc = sys.argv[1] if len(sys.argv) > 1 else "careers"
    c = make_canaries(sc)
    print(json.dumps(c, indent=2))
    print(f"\n{len(build_lookup(c))} searchable variants")
