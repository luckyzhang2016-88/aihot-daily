#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Push the daily Markdown summary to WeChat via ServerChan (Server酱).

Skipped silently when SERVERCHAN_SENDKEY is absent, so the workflow still
publishes Pages and sends email even if WeChat isn't configured.

Server酱 endpoints:
  - new (SendKey starts with SCT): https://sctapi.ftqq.com/<key>.send  (POST title+desp, desp=markdown)
  - old:                          https://sc.ftqq.com/<key>.send        (POST text+desp)
"""
import os
import sys
import json
import urllib.parse
import urllib.request

sendkey = os.environ.get("SERVERCHAN_SENDKEY", "")
path = sys.argv[1] if len(sys.argv) > 1 else "dist/summary.md"

if not sendkey:
    print("SERVERCHAN_SENDKEY not set - skipping WeChat push (Pages/email unaffected).")
    sys.exit(0)

try:
    with open(path, "r", encoding="utf-8") as f:
        md = f.read()
except OSError as e:
    print(f"WeChat push skipped: cannot read summary {path}: {e}")
    sys.exit(0)

# The first Markdown "# heading" becomes the message title; the rest is the body.
title = "AI 晨报"
for line in md.splitlines():
    line = line.strip()
    if line.startswith("# "):
        title = line[2:].strip()
        break
title = title[:100]
desp = md

if sendkey.upper().startswith("SCT"):
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = urllib.parse.urlencode({"title": title, "desp": desp}).encode("utf-8")
else:
    url = f"https://sc.ftqq.com/{sendkey}.send"
    data = urllib.parse.urlencode({"text": title, "desp": desp}).encode("utf-8")

req = urllib.request.Request(
    url, data=data,
    headers={"User-Agent": "aihot-daily/1.0", "Content-Type": "application/x-www-form-urlencoded"},
)
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode("utf-8"))
    if resp.get("code") in (0, "0"):
        print(f"ServerChan OK -> {title}")
    else:
        print(f"ServerChan returned error: {resp}")
        sys.exit(1)
except Exception as e:  # network / HTTP error
    print(f"WeChat push failed: {e}")
    sys.exit(1)
