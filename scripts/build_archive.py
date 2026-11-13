#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MediaCrawler 小红书 jsonl -> 单篇 Markdown 归档（幂等，仅标准库）。

格式规则见 xhs-archive skill 的 SKILL.md / RUNBOOK.md。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

CST = timezone(timedelta(hours=8))
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".heic", ".bmp"}

KNOWN_FIELDS = [
    "note_id", "type", "title", "desc", "video_url", "time",
    "last_update_time", "creator_hash", "nickname", "liked_count",
    "collected_count", "comment_count", "share_count", "image_list",
    "tag_list", "last_modify_ts", "note_url", "source_keyword", "xsec_token",
]


def iter_jsonl(paths):
    for p in paths:
        with p.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    print(f"[warn] {p.name}:{lineno} 非法 JSON，跳过", file=sys.stderr)
                    continue
                if isinstance(obj, dict):
                    yield obj


def collect_inputs(inputs, want_comments=False):
    files, seen = [], set()
    for raw in inputs:
        p = Path(raw)
        candidates = []
        if p.is_dir():
            candidates = sorted(q for q in p.rglob("*.jsonl")
                                if ("comment" in q.name.lower()) == want_comments)
        elif p.is_file():
            candidates = [p]
        else:
            candidates = [q for q in Path(".").glob(raw) if q.is_file()]
        for q in candidates:
            rp = str(q.resolve())
            if rp not in seen:
                seen.add(rp)
                files.append(q)
    return files


def parse_time(value, fallback=None):
    if fallback is None:
        fallback = datetime.now(CST)
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        v = float(value)
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return fallback
        if re.fullmatch(r"\d{10,17}", s):
            v = float(s)
        else:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(s[:19], fmt).replace(tzinfo=CST)
                except ValueError:
                    pass
            return fallback
    else:
        return fallback
    if v > 1e14:
        v /= 1e6
    if v > 1e11:
        v /= 1e3
    try:
        return datetime.fromtimestamp(v, CST)
    except (OSError, OverflowError, ValueError):
        return fallback


def num(v):
    if v is None or v == "":
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d+", str(v).replace(",", ""))
    return int(m.group()) if m else 0


def split_urls(v):
    if not v:
        return []
    if isinstance(v, list):
        return [str(x) for x in v if x]
    return [u.strip() for u in str(v).split(",") if u.strip()]


def yaml_str(v):
    return json.dumps(str(v if v is not None else ""), ensure_ascii=False)


def clean_title(title):
    t = str(title or "").strip().replace("\n", " ") or "笔记"
    t = re.sub(r'[/\\:*?"<>|]', "-", t)
    t = re.sub(r"\s+", " ", t).strip().strip(".")
    return t[:120].strip() or "笔记"


def safe_filename(title, month, used):
    base = f"{month} {clean_title(title)}"
    name = base
    n = 2
    while name in used:
        name = f"{base} ({n})"
        n += 1
    used.add(name)
    return name + ".md"


def sync_media(note_id, media_root, out, include_video=False):
    dest = out / "media" / note_id
    if dest.is_dir():
        local = sorted(p for p in dest.iterdir() if p.is_file())
        if local:
            return local
    if not media_root:
        return []
    for cand in (Path(media_root) / "xhs" / "media" / note_id,
                 Path(media_root) / "media" / note_id):
        if cand.is_dir() and any(cand.iterdir()):
            dest.mkdir(parents=True, exist_ok=True)
            for src in sorted(p for p in cand.iterdir() if p.is_file()):
                if src.suffix.lower() not in IMAGE_EXT and not include_video:
                    continue
                if not (dest / src.name).exists():
                    shutil.copy2(src, dest / src.name)
            return sorted(p for p in dest.iterdir() if p.is_file())
    return []


def load_comments(inputs):
    rows = []
    for obj in iter_jsonl(collect_inputs(inputs, want_comments=True)):
        if obj.get("comment_id"):
            rows.append(obj)
    return rows


def build_comment_lines(note_id, by_note, author_hash, stats):
    cs = by_note.get(str(note_id), [])
    if not cs:
        return []
    by_id = OrderedDict()
    for c in cs:
        cid = str(c.get("comment_id") or "")
        if cid:
            by_id[cid] = c
    author_ids = {cid for cid, c in by_id.items()
                  if str(c.get("creator_hash") or "") == author_hash}
    if not author_ids:
        return []

    groups = defaultdict(list)
    solo = []
    for cid in author_ids:
        c = by_id[cid]
        parent = str(c.get("parent_comment_id") or "")
        if parent and parent in by_id:
            groups[parent].append(cid)
        else:
            solo.append(cid)

    stats["author_comments"] += len(author_ids)
    stats["qa_groups"] += len(groups)
    stats["notes_with_author"] += 1

    def render_one(c, role):
        t = parse_time(c.get("create_time"), parse_time(c.get("last_modify_ts")))
        nick = str(c.get("nickname") or "").strip()
        who = f"{role}（{nick}）" if nick else role
        content = str(c.get("content") or "").strip().replace("\n", " ")
        pics = split_urls(c.get("pictures"))
        out = [f"**{who}** · {t.strftime('%Y-%m-%d %H:%M')}", "", content, ""]
        if pics:
            out += ["评论附图：" + " ".join(pics), ""]
        return out

    lines = ["## 评论区（博主相关）", ""]
    i = 0
    for root_id, reply_ids in sorted(groups.items(),
                                     key=lambda kv: parse_time(by_id[kv[0]].get("create_time"))):
        i += 1
        lines += [f"### 问答 {i}", ""]
        lines += render_one(by_id[root_id], "提问者")
        for rid in sorted(reply_ids, key=lambda x: parse_time(by_id[x].get("create_time"))):
            lines += render_one(by_id[rid], "博主")
    if solo:
        lines += ["### 博主主动评论", ""]
        for cid in sorted(solo, key=lambda x: parse_time(by_id[x].get("create_time"))):
            lines += render_one(by_id[cid], "博主")
    return lines


def render_body(note, dt, media_root, out, comment_lines, include_video=False):
    nid = str(note.get("note_id") or "")
    desc = str(note.get("desc") or "").strip()
    images = split_urls(note.get("image_list"))
    videos = split_urls(note.get("video_url"))
    note_url = str(note.get("note_url") or "")
    local = sync_media(nid, media_root, out, include_video)

    body = [f"发布时间：{dt.strftime('%Y-%m-%d %H:%M')}"]
    if note_url:
        body.append(f"[原帖链接]({note_url})")
    body.append("")
    if desc:
        body += [desc, ""]
    if local:
        body += ["## 图片", ""]
        for f in local:
            rel = Path("..") / "media" / nid / f.name
            body.append(f"![]({rel.as_posix()})")
        body.append("")
    elif images:
        body += ["## 图片（原始链接，可能过期）", ""]
        body += [f"- 图 {i}: {u}" for i, u in enumerate(images, 1)]
        body.append("")
    if videos and not include_video:
        body += [f"该笔记含视频，按要求未下载视频文件（{len(videos)} 个）。", ""]
    if comment_lines:
        body += comment_lines
    return body


def render_note(note, dt, media_root, out, comment_lines, display_title, include_video=False):
    nid = str(note.get("note_id") or "")
    raw_title = str(note.get("title") or "").strip().replace("\n", " ")
    tags = split_urls(note.get("tag_list"))
    note_url = str(note.get("note_url") or "")
    fm = [
        "---",
        f"note_id: {yaml_str(nid)}",
        f"title: {yaml_str(raw_title)}",
        f"type: {yaml_str(note.get('type'))}",
        f"time: {dt.strftime('%Y-%m-%d %H:%M:%S')}",
        f"liked: {num(note.get('liked_count'))}",
        f"collected: {num(note.get('collected_count'))}",
        f"comment: {num(note.get('comment_count'))}",
        f"share: {num(note.get('share_count'))}",
        "tags: [" + ", ".join(yaml_str(t) for t in tags) + "]",
        f"source: {yaml_str(note_url)}",
        "---",
        "",
        f"# {display_title}",
        "",
    ]
    return "\n".join(fm + render_body(note, dt, media_root, out, comment_lines, include_video))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", nargs="+", required=True, help="笔记 jsonl 文件或目录")
    ap.add_argument("--comments", nargs="*", default=[], help="评论 jsonl 文件或目录")
    ap.add_argument("--out", required=True, help="归档输出目录")
    ap.add_argument("--name", default="", help="博主名（用于 index.md）")
    ap.add_argument("--media-root", default="", help="MediaCrawler 媒体根目录")
    ap.add_argument("--source-url", default="", help="博主主页链接")
    ap.add_argument("--author-hash", default="", help="博主 creator_hash（留空则从 --source-url 自动推算）")
    ap.add_argument("--include-video", action="store_true", help="连视频文件一起归档（默认跳过）")
    args = ap.parse_args()

    if not args.author_hash and args.source_url:
        import hashlib
        m = re.search(r"/user/profile/([0-9A-Za-z_-]+)", args.source_url)
        if m:
            args.author_hash = hashlib.sha256(m.group(1).encode("utf-8")).hexdigest()[:16]
            print(f"[info] 从主页链接推算 author_hash = {args.author_hash}")


    out = Path(args.out).resolve()
    (out / "notes").mkdir(parents=True, exist_ok=True)

    inputs = collect_inputs(args.input, want_comments=False)
    if not inputs:
        print("[error] 没有找到笔记 jsonl 输入文件", file=sys.stderr)
        return 2
    print("[info] 笔记输入 " + str(len(inputs)) + " 个: " + ", ".join(p.name for p in inputs))

    comment_rows = load_comments(args.comments) if args.comments else []
    by_note = defaultdict(list)
    for c in comment_rows:
        by_note[str(c.get("note_id") or "")].append(c)
    print(f"[info] 评论输入 {len(comment_rows)} 条，覆盖 {len(by_note)} 篇笔记")

    raw_rows, notes = [], OrderedDict()
    for obj in iter_jsonl(inputs):
        raw_rows.append(obj)
        if obj.get("comment_id") or not obj.get("note_id"):
            continue
        notes[str(obj["note_id"])] = obj

    for p in list((out / "notes").glob("*.md")):
        p.unlink()
    raw_dir = out / "raw"
    if raw_dir.is_dir():
        for p in raw_dir.glob("*.md"):
            p.unlink()
        try:
            raw_dir.rmdir()
        except OSError:
            pass

    by_month = {}
    for nid, note in notes.items():
        dt = parse_time(note.get("time"), parse_time(note.get("last_modify_ts")))
        by_month.setdefault(dt.strftime("%Y-%m"), []).append((dt, nid, note))
    for month in by_month:
        by_month[month].sort(key=lambda x: x[0])

    used = set()
    note_files = {}
    for month in sorted(by_month):
        for dt, nid, note in by_month[month]:
            note_files[nid] = safe_filename(note.get("title"), month, used)

    stats2 = {"author_comments": 0, "qa_groups": 0, "notes_with_author": 0}
    for month in sorted(by_month):
        for dt, nid, note in by_month[month]:
            cl = build_comment_lines(nid, by_note, args.author_hash, stats2)
            fname = note_files[nid]
            (out / "notes" / fname).write_text(
                render_note(note, dt, args.media_root, out, cl, fname[:-3], args.include_video),
                encoding="utf-8")

    with (out / "data.jsonl").open("w", encoding="utf-8") as f:
        for note in notes.values():
            f.write(json.dumps(note, ensure_ascii=False) + "\n")
    (out / "data.raw.json").write_text(
        json.dumps(raw_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "comments.raw.json").write_text(
        json.dumps(comment_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    all_dt = [parse_time(n.get("time"), parse_time(n.get("last_modify_ts"))) for n in notes.values()]
    span = (min(all_dt).strftime("%Y-%m-%d"), max(all_dt).strftime("%Y-%m-%d")) if all_dt else ("-", "-")

    missing = {k: sum(1 for n in notes.values() if n.get(k) in (None, "", [], 0)) for k in KNOWN_FIELDS}
    report = [f"笔记数: {len(notes)}", f"原始行: {len(raw_rows)}",
              f"评论原始行: {len(comment_rows)}", f"单篇文件数: {len(note_files)}",
              f"月份分组: {len(by_month)}", f"时间跨度: {span[0]} ~ {span[1]}",
              f"博主评论: {stats2['author_comments']}",
              f"问答组: {stats2['qa_groups']}",
              f"有博主互动的笔记: {stats2['notes_with_author']}",
              "字段缺失: " + ", ".join(f"{k}={v}" for k, v in missing.items() if v)]
    if stats2["author_comments"] == 0:
        report.append("[warn] 未识别到任何博主评论：creator_hash 判据可能失效，请检查评论原始 user_id")
        print("[warn] 未识别到任何博主评论，检查 creator_hash 判据", file=sys.stderr)
    print("\n".join(report))
    print(f"[ok] 归档已生成: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
