#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a single-file HTML morning dashboard from the AI HOT daily report.

Usage:
    python3 generate_daily.py                 # today (Asia/Shanghai)
    python3 generate_daily.py 2026-09-04      # a specific date
    python3 generate_daily.py -o out.html     # custom output path

Stdlib only, so it runs identically on a laptop and inside GitHub Actions.
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://aihot.virxact.com/api/v1"
UA = "aihot-daily-dashboard/1.0 (+https://aihot.virxact.com)"
BEIJING = dt.timezone(dt.timedelta(hours=8))

SECTIONS = ["模型发布/更新", "产品发布/更新", "行业动态", "论文研究", "技巧与观点"]
SLUG = {
    "模型发布/更新": "model",
    "产品发布/更新": "product",
    "行业动态": "industry",
    "论文研究": "paper",
    "技巧与观点": "insight",
}
DESC = {
    "模型发布/更新": "新模型、权重与能力更新",
    "产品发布/更新": "工具、平台与功能上线",
    "行业动态": "融资、收购与生态格局",
    "论文研究": "新论文与研究方法",
    "技巧与观点": "评测、实践与评论",
}
ABSTRACT_MAX = 60


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def get(path, **params):
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"__error__": e.code}
    except Exception as e:  # network hiccup -> caller degrades gracefully
        return {"__error__": str(e)}


# --------------------------------------------------------------------------
# time helpers
# --------------------------------------------------------------------------
def parse(iso):
    if not iso:
        return None
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))


def human_time(iso, kind, ref_date):
    """UTC -> Beijing time, phrased for humans. Date-only sources get no clock."""
    d = parse(iso)
    if not d:
        return "时间待补"
    b = d.astimezone(BEIJING)
    if b.date() == ref_date:
        day = "今天"
    elif b.date() == ref_date - dt.timedelta(days=1):
        day = "昨天"
    else:
        day = f"{b.month}月{b.day}日"
    label = "原文发布" if kind == "published" else "AI HOT 收录"
    # sources that only publish a date land on exactly 00:00:00Z
    if (d.hour, d.minute, d.second) == (0, 0, 0):
        return f"{day}（原文仅标注日期）", label
    h = b.hour
    slot = "凌晨" if h < 6 else "上午" if h < 12 else "下午" if h < 18 else "晚上"
    clock = f"{h % 12 if h % 12 else 12}:{b.minute:02d}"
    return f"{day} {slot}{clock}", label


# --------------------------------------------------------------------------
# abstract compression
# --------------------------------------------------------------------------
_SENT_END = "。！？"   # safe to cut after: a complete thought
_CLAUSE_END = "；"      # acceptable second choice
_TAIL_JUNK = "，、；： "


def fit_abstract(text, title=""):
    """Compress to <= ABSTRACT_MAX characters, preferring a clean sentence break.

    Never cut right after 、or ，-- that would leave a dangling enumeration
    ("支持 A、B、C。" reads as if C were the last item when it isn't).
    """
    t = re.sub(r"\s+", " ", (text or "")).strip()
    if not t:
        t = (title or "").strip()
    if len(t) <= ABSTRACT_MAX:
        return t or "原文未提供摘要。"

    head = t[:ABSTRACT_MAX]
    for pool, keep in ((_SENT_END, True), (_CLAUSE_END, False)):
        idx = max(head.rfind(ch) for ch in pool)
        if idx >= 30:
            return head[: idx + 1] if keep else head[:idx].rstrip(_TAIL_JUNK) + "。"
    return head[: ABSTRACT_MAX - 1].rstrip(_TAIL_JUNK) + "…"


def keyword_of(title):
    """Pick a search keyword for backfilling a missing timestamp."""
    words = re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-]{2,}", title or "")
    if words:
        return max(words, key=len)
    return (title or "")[:6]


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------
def fetch_daily(date_str):
    """Fetch the daily for `date_str`; fall back to the newest available issue."""
    res = get(f"/dailies/{date_str}")
    if "__error__" not in res:
        return res.get("report"), date_str, False
    if res.get("__error__") != 404:
        return None, date_str, False
    idx = get("/dailies", limit=7)
    rows = idx.get("items") or idx.get("dailies") or []
    dates = sorted({r.get("date") for r in rows if r.get("date")}, reverse=True)
    if not dates:
        return None, date_str, False
    res2 = get(f"/dailies/{dates[0]}")
    if "__error__" in res2:
        return None, date_str, False
    return res2.get("report"), dates[0], True


def backfill_times(report):
    """Daily items carry no timestamp; match them against the items API."""
    pool = {}
    for window in ("24h", "7d"):
        res = get("/items", mode="selected", window=window, limit=50)
        for it in res.get("items", []) or []:
            u = (it.get("links") or {}).get("aihot")
            if u:
                pool[u.rstrip("/").split("/")[-1]] = it

    def fill(store):
        missing = []
        for sec in report["sections"]:
            for it in sec["items"]:
                pid = ((it.get("links") or {}).get("aihot") or "").rstrip("/").split("/")[-1]
                src = store.get(pid)
                if src:
                    it["publishedAt"] = src.get("publishedAt")
                    it["discoveredAt"] = src.get("discoveredAt")
                elif not it.get("publishedAt") and not it.get("discoveredAt"):
                    missing.append((pid, it))
        return missing

    missing = fill(pool)
    # second pass: keyword lookup in the full pool for whatever is still blank
    for pid, it in missing[:8]:
        res = get("/items", mode="all", window="7d", limit=50, q=keyword_of(it.get("title", "")))
        for cand in res.get("items", []) or []:
            u = (cand.get("links") or {}).get("aihot") or ""
            if u.rstrip("/").split("/")[-1] == pid:
                it["publishedAt"] = cand.get("publishedAt")
                it["discoveredAt"] = cand.get("discoveredAt")
                break
    return report


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------
CSS = """
  :root{
    --teal:#E8833A;--teal-dark:#C06A1C;--teal-soft:#FCEDE0;--teal-line:#F3D8C3;
    --ink:#332318;--ink-2:#5C4736;--ink-3:#9A8472;--line:#F1E3D7;--bg:#FFF9F3;--card:#fff;
    --model:#E8833A;--product:#4A90D9;--industry:#E0A52E;--paper:#9B6BC9;--insight:#D9536B;
    --radius:16px;--shadow:0 1px 2px rgba(20,48,46,.04),0 8px 24px rgba(20,48,46,.06);
    --shadow-hi:0 4px 8px rgba(20,48,46,.06),0 18px 40px rgba(232,131,58,.16);
  }
  *{box-sizing:border-box}
  html{scroll-behavior:smooth;scroll-padding-top:92px}
  body{margin:0;background:var(--bg);color:var(--ink);font-size:15px;line-height:1.65;
    -webkit-font-smoothing:antialiased;
    font-family:"Sarasa Gothic SC","Sarasa Gothic",-apple-system,BlinkMacSystemFont,
    "PingFang SC","Hiragino Sans GB","Microsoft YaHei","Source Han Sans SC","Noto Sans CJK SC",sans-serif}
  a{color:inherit}
  .wrap{max-width:1180px;margin:0 auto;padding:0 20px 64px}
  .hero{position:relative;overflow:hidden;background:linear-gradient(135deg,#FDEEE2 0%,#FCF4EC 45%,#fff 100%);
    border-bottom:1px solid var(--line)}
  .hero::after{content:"";position:absolute;right:-140px;top:-160px;width:460px;height:460px;border-radius:50%;
    background:radial-gradient(circle,rgba(232,131,58,.16) 0%,rgba(232,131,58,0) 70%)}
  .hero-inner{max-width:1180px;margin:0 auto;padding:44px 20px 30px;position:relative;z-index:1}
  .kicker{display:inline-flex;align-items:center;gap:8px;font-size:12px;letter-spacing:.14em;
    color:var(--teal-dark);background:#fff;border:1px solid var(--teal-line);padding:5px 12px;
    border-radius:999px;font-weight:600}
  .kicker .pulse{width:7px;height:7px;border-radius:50%;background:var(--teal);
    animation:pulse 2.2s infinite}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(232,131,58,.45)}70%{box-shadow:0 0 0 9px rgba(232,131,58,0)}
    100%{box-shadow:0 0 0 0 rgba(232,131,58,0)}}
  h1{font-size:34px;line-height:1.25;margin:16px 0 6px;letter-spacing:-.01em}
  h1 .accent{color:var(--teal-dark)}
  .hero-date{font-size:16px;color:var(--ink-2);font-weight:600}
  .hero-meta{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:14px;font-size:13px;color:var(--ink-3)}
  .hero-meta b{color:var(--ink-2);font-weight:600}
  .hero-total{display:inline-flex;align-items:baseline;gap:8px;margin-top:20px;background:#fff;
    border:1px solid var(--line);border-radius:14px;padding:12px 20px;box-shadow:var(--shadow)}
  .hero-total .big{font-size:40px;font-weight:700;color:var(--teal-dark);line-height:1}
  .hero-total .lbl{font-size:13px;color:var(--ink-3)}
  .stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:24px}
  .stat-card{display:block;text-decoration:none;background:#fff;border:1px solid var(--line);
    border-radius:var(--radius);padding:14px 14px 12px;box-shadow:var(--shadow);
    transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}
  .stat-card:hover{transform:translateY(-3px);box-shadow:var(--shadow-hi);border-color:var(--teal-line)}
  .stat-card.is-empty{opacity:.62;background:#FCFEFE}
  .stat-top{display:flex;align-items:center;gap:7px}
  .stat-name{font-size:13px;font-weight:600;color:var(--ink-2)}
  .stat-num{font-size:26px;font-weight:700;margin-top:6px;line-height:1.1}
  .stat-unit{font-size:12px;font-weight:500;color:var(--ink-3);margin-left:3px}
  .stat-bar{height:4px;background:#EEF5F4;border-radius:999px;margin:8px 0 7px;overflow:hidden}
  .stat-bar i{display:block;height:100%;border-radius:999px;background:var(--teal)}
  .stat-foot{font-size:11.5px;color:var(--ink-3);line-height:1.5}
  .stat-dot,.sec-dot,.nav-dot{width:9px;height:9px;border-radius:50%;display:inline-block;flex:none}
  .d-model{background:var(--model)}.d-product{background:var(--product)}
  .d-industry{background:var(--industry)}.d-paper{background:var(--paper)}.d-insight{background:var(--insight)}
  .nav{position:sticky;top:0;z-index:20;background:rgba(245,250,249,.88);
    backdrop-filter:saturate(1.6) blur(10px);border-bottom:1px solid var(--line)}
  .nav-inner{max-width:1180px;margin:0 auto;padding:10px 20px;display:flex;gap:8px;
    overflow-x:auto;scrollbar-width:none}
  .nav-inner::-webkit-scrollbar{display:none}
  .nav-chip{display:inline-flex;align-items:center;gap:7px;flex:none;text-decoration:none;font-size:13px;
    font-weight:600;color:var(--ink-2);background:#fff;border:1px solid var(--line);border-radius:999px;
    padding:7px 13px;transition:all .16s ease;white-space:nowrap}
  .nav-chip:hover{border-color:var(--teal-line);color:var(--teal-dark)}
  .nav-chip.is-empty{opacity:.55}
  .nav-chip.active{background:var(--teal);border-color:var(--teal);color:#fff}
  .nav-chip.active .nav-dot{background:#fff!important}
  .nav-count{font-size:11px;font-weight:700;background:#EEF5F4;color:var(--ink-2);border-radius:999px;
    padding:1px 7px;min-width:20px;text-align:center}
  .nav-chip.active .nav-count{background:rgba(255,255,255,.24);color:#fff}
  .sec{padding-top:38px}
  .sec-head{margin-bottom:16px}
  .sec-title-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .sec-title-row h2{font-size:21px;margin:0;letter-spacing:-.01em}
  .sec-count{font-size:12px;font-weight:700;color:var(--teal-dark);background:var(--teal-soft);
    border-radius:999px;padding:2px 10px}
  .sec-range{font-size:12px;color:var(--ink-3);font-variant-numeric:tabular-nums}
  .sec-desc{margin:5px 0 0 19px;font-size:13px;color:var(--ink-3)}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:14px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:var(--radius);
    padding:16px 16px 13px;box-shadow:var(--shadow);display:flex;flex-direction:column;
    transition:transform .18s ease,box-shadow .18s ease,border-color .18s ease}
  .card:hover{transform:translateY(-3px);box-shadow:var(--shadow-hi);border-color:var(--teal-line)}
  .card-head{display:flex;align-items:center;gap:9px;margin-bottom:9px}
  .card-num{font-size:12px;font-weight:800;color:#fff;background:var(--teal);border-radius:7px;
    padding:2px 8px;font-variant-numeric:tabular-nums;flex:none}
  .card-src{font-size:11.5px;color:var(--ink-2);background:#F1F7F6;border:1px solid var(--line);
    border-radius:999px;padding:2px 9px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .card-title{font-size:15.5px;line-height:1.5;margin:0 0 9px;font-weight:650}
  .card-title a{text-decoration:none;color:var(--ink)}
  .card-title a:hover{color:var(--teal-dark);text-decoration:underline;text-underline-offset:3px}
  .card-abs{margin:0 0 13px;font-size:13.5px;color:var(--ink-2);line-height:1.68}
  .card-foot{margin-top:auto;display:flex;align-items:center;justify-content:space-between;gap:10px;
    padding-top:10px;border-top:1px dashed var(--line)}
  .card-time{font-size:12px;color:var(--ink-3);font-variant-numeric:tabular-nums}
  .card-time em{font-style:normal;margin-left:6px;color:#A9BEBB}
  .card-orig{font-size:12px;font-weight:600;color:var(--teal-dark);text-decoration:none;
    border:1px solid var(--teal-line);border-radius:999px;padding:3px 10px;flex:none;transition:background .16s ease}
  .card-orig:hover{background:var(--teal-soft)}
  .empty{grid-column:1/-1;border:1px dashed var(--teal-line);border-radius:var(--radius);
    background:#FCFEFE;padding:26px 22px;color:var(--ink-2);font-size:13.5px}
  .empty-icon{font-size:22px;color:var(--teal);margin-bottom:6px}
  .empty p{margin:4px 0}
  .empty p:last-child{color:var(--ink-3);font-size:12.5px}
  footer{margin-top:52px;padding-top:22px;border-top:1px solid var(--line);color:var(--ink-3);font-size:13px}
  .foot-row{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:center}
  .foot-total{display:inline-flex;align-items:baseline;gap:6px;font-size:15px;font-weight:700;color:var(--teal-dark)}
  footer a{color:var(--teal-dark);text-decoration:none;font-weight:600}
  footer a:hover{text-decoration:underline}
  .foot-note{margin-top:12px;font-size:12px;line-height:1.7;color:#9BB2AE}
  @media (max-width:900px){.stats{grid-template-columns:repeat(3,1fr)}}
  @media (max-width:640px){
    html{scroll-padding-top:76px}
    h1{font-size:26px}
    .hero-inner{padding:32px 16px 24px}
    .wrap{padding:0 16px 48px}
    .nav-inner{padding:9px 16px}
    .stats{grid-template-columns:repeat(2,1fr)}
    .grid{grid-template-columns:1fr}
    .hero-total .big{font-size:32px}
    .card-time em{display:none}
  }
  @media print{.nav{display:none}.card,.stat-card{box-shadow:none;break-inside:avoid}}
"""

JS = """
(function(){
  var chips = Array.prototype.slice.call(document.querySelectorAll('.nav-chip'));
  var secs = chips.map(function(c){ return document.querySelector(c.getAttribute('href')); });
  function setActive(id){
    chips.forEach(function(c){ c.classList.toggle('active', c.getAttribute('href') === '#' + id); });
  }
  chips.forEach(function(c){
    c.addEventListener('click', function(){ setActive(c.getAttribute('href').slice(1)); });
  });
  var ticking = false;
  function onScroll(){
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(function(){
      var offset = 140, current = secs[0];
      secs.forEach(function(s){ if (s && s.getBoundingClientRect().top <= offset) current = s; });
      if (current) setActive(current.id);
      ticking = false;
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
  var cards = document.querySelectorAll('.card');
  if ('IntersectionObserver' in window){
    var io = new IntersectionObserver(function(entries){
      entries.forEach(function(e){
        if (e.isIntersecting){
          e.target.style.opacity = '1';
          e.target.style.transform = 'none';
          io.unobserve(e.target);
        }
      });
    }, { rootMargin: '0px 0px -40px 0px' });
    cards.forEach(function(c, i){
      c.style.opacity = '0';
      c.style.transform = 'translateY(10px)';
      c.style.transition = 'opacity .4s ease ' + (i % 6) * 40 + 'ms, transform .4s ease ' +
                           (i % 6) * 40 + 'ms, box-shadow .18s ease, border-color .18s ease';
      io.observe(c);
    });
  }
})();
"""


def render(report, date_str, fell_back):
    ref_date = dt.date.fromisoformat(date_str)
    weekday = "一二三四五六日"[ref_date.weekday()]
    canonical = report.get("links", {}).get("aihot") or "https://aihot.virxact.com"

    buckets = {s: [] for s in SECTIONS}
    for sec in report.get("sections", []):
        buckets.setdefault(sec["label"], []).extend(sec["items"])
    for label in [k for k in buckets if k not in SECTIONS]:
        buckets.setdefault("技巧与观点", []).extend(buckets.pop(label))

    cards = {s: [] for s in SECTIONS}
    n = 0
    for s in SECTIONS:
        for it in buckets.get(s, []):
            n += 1
            cards[s].append((n, it))
    total = n

    gen = parse(report.get("generatedAt"))
    gb = gen.astimezone(BEIJING) if gen else None
    gen_disp = f"{gb.month}月{gb.day}日 {gb.hour:02d}:{gb.minute:02d}" if gb else "—"
    ws, we = parse(report.get("windowStart")), parse(report.get("windowEnd"))
    win_disp = ""
    if ws and we:
        a, b = ws.astimezone(BEIJING), we.astimezone(BEIJING)
        win_disp = (f"{a.month}月{a.day}日 {a.hour:02d}:{a.minute:02d} — "
                    f"{b.month}月{b.day}日 {b.hour:02d}:{b.minute:02d}")

    # nav
    nav = []
    for s in SECTIONS:
        c = len(cards[s])
        nav.append(f'<a class="nav-chip{" is-empty" if c == 0 else ""}" href="#sec-{SLUG[s]}">'
                   f'<span class="nav-dot d-{SLUG[s]}"></span>{html.escape(s)}'
                   f'<span class="nav-count">{c}</span></a>')

    # hero stats
    stats = []
    for s in SECTIONS:
        c = len(cards[s])
        rng = f"{cards[s][0][0]:02d}–{cards[s][-1][0]:02d} 号" if c else "本期暂无"
        pct = (c / total * 100) if total else 0
        stats.append(f"""
        <a class="stat-card{" is-empty" if c == 0 else ""}" href="#sec-{SLUG[s]}">
          <div class="stat-top"><span class="stat-dot d-{SLUG[s]}"></span><span class="stat-name">{html.escape(s)}</span></div>
          <div class="stat-num">{c}<span class="stat-unit">条</span></div>
          <div class="stat-bar"><i style="width:{pct:.1f}%"></i></div>
          <div class="stat-foot">{html.escape(rng)} · {html.escape(DESC[s])}</div>
        </a>""")

    # body
    body = []
    for s in SECTIONS:
        items = cards[s]
        rng = f"No.{items[0][0]:02d}–{items[-1][0]:02d}" if items else "No.—"
        grid = []
        for num, it in items:
            title = html.escape((it.get("title") or "").strip())
            src = html.escape((it.get("source") or {}).get("name", "未标注来源"))
            aihot = html.escape((it.get("links") or {}).get("aihot") or canonical, quote=True)
            orig = (it.get("links") or {}).get("original")
            abstract = html.escape(fit_abstract(it.get("summary"), it.get("title")))

            if it.get("publishedAt"):
                tdisp, tlabel = human_time(it["publishedAt"], "published", ref_date)
            elif it.get("discoveredAt"):
                tdisp, tlabel = human_time(it["discoveredAt"], "discovered", ref_date)
            else:
                tdisp, tlabel = "本期收录", "收录"

            orig_html = (f'<a class="card-orig" href="{html.escape(orig, quote=True)}" '
                         f'target="_blank" rel="noopener noreferrer">原文 ↗</a>') if orig else ""

            grid.append(f"""
          <article class="card">
            <div class="card-head">
              <span class="card-num">{num:02d}</span>
              <span class="card-src">{src}</span>
            </div>
            <h3 class="card-title"><a href="{aihot}" target="_blank" rel="noopener noreferrer">{title}</a></h3>
            <p class="card-abs">{abstract}</p>
            <div class="card-foot">
              <span class="card-time" title="{html.escape(tlabel)}">{tdisp}<em>{html.escape(tlabel)}</em></span>
              {orig_html}
            </div>
          </article>""")

        empty = ""
        if not items:
            empty = """
          <div class="empty">
            <div class="empty-icon">◇</div>
            <p><strong>本期没有收录该版块的条目。</strong></p>
            <p>AI HOT 日报按当日实际收录情况分版块，某一版块为空属于正常情况，不代表该领域当日无进展。</p>
          </div>"""

        body.append(f"""
      <section class="sec" id="sec-{SLUG[s]}">
        <header class="sec-head">
          <div class="sec-title-row">
            <span class="sec-dot d-{SLUG[s]}"></span>
            <h2>{html.escape(s)}</h2>
            <span class="sec-count">{len(items)} 条</span>
            <span class="sec-range">{rng}</span>
          </div>
          <p class="sec-desc">{html.escape(DESC[s])}</p>
        </header>
        <div class="grid">{''.join(grid)}{empty}</div>
      </section>""")

    fallback_note = ""
    if fell_back:
        fallback_note = (f'<p class="foot-note">注意：{date_str} 当天日报尚未生成，'
                         f'本期内容为最近一期已发布日报（{report.get("date")}）。</p>')

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>AI 晨报 · {date_str} · AI HOT 日报</title>
<style>{CSS}</style>
</head>
<body>
<header class="hero">
  <div class="hero-inner">
    <span class="kicker"><span class="pulse"></span>AI HOT · 每日 AI 晨报</span>
    <h1>今日 AI 圈 <span class="accent">{total} 条</span>重点，一次看完</h1>
    <div class="hero-date">{ref_date.year} 年 {ref_date.month} 月 {ref_date.day} 日 · 星期{weekday}</div>
    <div class="hero-meta">
      <span>日报生成：<b>{html.escape(gen_disp)}</b>（北京时间）</span>
      <span>覆盖窗口：<b>{html.escape(win_disp)}</b></span>
      <span>版块：<b>5</b> 个</span>
    </div>
    <div class="hero-total">
      <span class="big">{total}</span>
      <span class="lbl">条精选<br>连续编号 01–{total:02d}</span>
    </div>
    <div class="stats">{''.join(stats)}</div>
  </div>
</header>
<nav class="nav"><div class="nav-inner">{''.join(nav)}</div></nav>
<main class="wrap">{''.join(body)}
  <footer>
    <div class="foot-row">
      <span class="foot-total">共 {total} 条</span>
      <span>数据源：<a href="{html.escape(canonical, quote=True)}" target="_blank" rel="noopener noreferrer">AI HOT 日报 · {date_str}</a></span>
      <span>生成时间：{html.escape(gen_disp)}（北京时间）</span>
    </div>
    {fallback_note}
    <p class="foot-note">
      本页由 AI HOT 公开日报接口数据渲染，内容版权归原作者所有，摘要为自动压缩后的中文改写，引用数字与原话请回原文核对。<br>
      时间为北京时间（UTC+8）；标注「原文发布」的取自第三方原文发布时间，标注「AI HOT 收录」的表示该条未公布原文时间。
    </p>
  </footer>
</main>
<script>{JS}</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="Generate an AI HOT daily HTML dashboard.")
    ap.add_argument("date", nargs="?", help="YYYY-MM-DD (default: today in Asia/Shanghai)")
    ap.add_argument("-o", "--out", help="output HTML path")
    args = ap.parse_args()

    date_str = args.date or dt.datetime.now(BEIJING).strftime("%Y-%m-%d")
    out = args.out or f"aihot-daily-{date_str}.html"

    report, used_date, fell_back = fetch_daily(date_str)
    if not report:
        print(f"ERROR: no AI HOT daily available for {date_str}", file=sys.stderr)
        sys.exit(1)

    backfill_times(report)
    doc = render(report, used_date, fell_back)
    with open(out, "w", encoding="utf-8") as f:
        f.write(doc)

    counts = {s: 0 for s in SECTIONS}
    for sec in report.get("sections", []):
        counts[sec["label"]] = len(sec["items"])
    print(f"OK {out}")
    print(f"date={used_date} fallback={'yes' if fell_back else 'no'} "
          f"total={sum(len(s['items']) for s in report['sections'])}")
    print("sections: " + " | ".join(f"{k}={counts.get(k, 0)}" for k in SECTIONS))


if __name__ == "__main__":
    main()
