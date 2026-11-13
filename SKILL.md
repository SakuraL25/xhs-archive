---
name: xhs-archive
description: "把某个小红书博主的全部公开笔记归档成单篇 Markdown（正文原文 + 本地图片 + 只保留博主本人评论及被博主回复的问答对）。按 --out 输出到指定目录，格式固定，不生成 index / build_report / raw 版。只要消息里出现 xiaohongshu.com 用户主页链接并提到「归档 / 全量 / 导出 / 备份笔记 / 进 wiki」，就默认自动使用本 skill，不需要用户 @ 或点名。需要 Chrome 远程调试开关与人工登录。"
description_en: "Archive a Xiaohongshu creator public notes into per-note Markdown in a configurable output directory."
agent_created: true
---

# 小红书博主全量归档（固定格式）

> **格式约定（勿擅改）**：输出目录由 `--out` 指定，格式固定为下面「最终格式规格」。不擅自改目录、不调整格式、不另出 llm-wiki raw 版。

## 固定约定

| 项 | 固定值 |
|---|---|
| 归档输出目录 | `<OUT_DIR>`（由 `--out` 指定） |
| 中间数据目录 | `<WORK_DIR>`（jsonl + 媒体缓存） |
| 最终格式 | 见「最终格式规格」，9 条规则 |
| 不生成的产物 | `index.md`、`build_report.md`、`raw/` 月卷、任何汇总/索引文件 |
| llm-wiki raw | **不做**。本 skill 只产出可读归档，不转 raw、不搬进任何库的 `raw/` |

## 触发

看到 `xiaohongshu.com/user/profile/...` 链接 + 归档 / 全量 / 导出 / 备份 / 进 wiki 意图，直接开工，不要问要不要用；输出目录取 `--out`。

## 输入参数

| 变量 | 必填 | 默认 | 说明 |
|---|---|---|---|
| CREATOR_URL | 是 | - | 博主主页完整链接，必须带 xsec_token 与 xsec_source |
| OUT_DIR | 是 | - | 归档输出目录，传给 `--out` |
| NAME | 否 | 空 | 仅占位保留；当前不写入任何产物（原 index.md 已取消） |
| WORK_DIR | 否 | `<WORK_DIR>` | 中间数据，固定 |
| MAX_NOTES | 否 | 2000 | 笔记数上限（默认 15 太小，必须调大） |
| COMMENTS_LIMIT | 否 | 100 | 每篇一级评论上限 |
| AUTHOR_HASH | 否 | 自动算 | sha256(user_id)[:16]，见「博主身份」 |

输出目录由 `--out` 指定，不硬编码任何本机路径。

## 前置环境

- Python 3.12 venv + MediaCrawler（已验证版本），依赖装 requirements.txt。
- 本机 Chrome 144+（157 已验证）；系统 python 常是 WindowsApps 占位，一律用 venv 绝对路径。
- 转换脚本 `scripts/build_archive.py` 只用标准库，skill 自包含；与工作区 `xhs-archive/build_archive.py` 保持同步。

## 人工步骤（不可由 agent 代做）

1. Chrome 里登录小红书（扫码）。
2. 打开 `chrome://inspect/#remote-debugging`，勾选 Allow remote debugging for this browser instance，看到 Server running at: 127.0.0.1:9222。
3. 采集时 Chrome 若弹确认框，点「接受」。
4. 出现滑块 / 验证码 / 限流 / 空结果：立即停机，交回人工，不反复重试。
5. 跑完把远程调试开关取消勾选——该开关允许外部应用读取 cookie 与站点数据，不要长期开着。

## 采集

```
cd <MediaCrawler 目录>
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY http_proxy https_proxy all_proxy no_proxy
PYTHONIOENCODING=utf-8 <venv python> main.py \
  --platform xhs --lt qrcode --type creator \
  --creator_id "<CREATOR_URL>" \
  --save_data_option jsonl \
  --save_data_path "<WORK_DIR>" \
  --get_media true --get_comment true --get_sub_comment true \
  --max_comments_count_singlenotes <COMMENTS_LIMIT> \
  --crawler_max_notes_count <MAX_NOTES> --max_concurrency_num 1
```

- 必须 `--get_sub_comment true`：博主的回答是二级评论，不开就抓不到。
- 并发 1、间隔 2 秒，保持低频；CDP 模式复用已登录 Chrome，不关闭用户浏览器。
- 先限制 5 条试跑，验证 creator_hash 命中 > 0 再放开全量。
- 输出 `<WORK_DIR>/xhs/jsonl/creator_contents_<日期>.jsonl` 与 `creator_comments_<日期>.jsonl`；媒体在 `<WORK_DIR>/xhs/media/<note_id>/`。

## 博主身份（关键）

教学版把 user_id 匿名化（`anonymize_user_id` = sha256 前 16 位）、昵称脱敏，存进 `creator_hash`。博主 user_id 从 CREATOR_URL 的 `/user/profile/<id>` 取，正向算一次：

```
python -c "import hashlib; print(hashlib.sha256('<user_id>'.encode()).hexdigest()[:16])"
```

把结果传给 `--author-hash`。脚本 stdout 命中 0 条会报警，说明 API 返回的 user_id 与主页链接不一致，需换判据。不改上游源码。

## 转换（输出目录写死）

```
<venv python> scripts/build_archive.py \
  --input "<WORK_DIR>/xhs/jsonl" \
  --comments "<WORK_DIR>/xhs/jsonl" \
  --out "<OUT_DIR>" \
  --name "<NAME>" \
  --source-url "<CREATOR_URL>" \
  --media-root "<WORK_DIR>" \
  --author-hash <AUTHOR_HASH>
```

脚本幂等，可重复跑；`data.jsonl` 是唯一真源，Markdown 随时可重建。不重新采集也能只重跑转换（改格式时就这么做）。

## 最终格式规格（9 条，固定，勿改）

1. **一篇一个 md**，放在 `notes/`，文件名与 H1 = `YYYY-MM <标题>`；标题里的 `/ \ : * ? " < > |` 一律换成 `-`，截断 120 字符，同月同名加 `(2)(3)`。
2. **无卷首 H1、无「共 N 篇」**，不生成月卷。
3. 发布时间行只有 `发布时间：YYYY-MM-DD HH:MM`，**下一行紧跟** `[原帖链接](url)`；不显示类型 / 赞 / 藏 / 评。
4. `desc` 原文原样保留（含 `#ict[话题]#` 等标签），**只删脚本补的** `#标签` 行。
5. 图片小节标题为 `## 图片`，图片在 `media/<note_id>/`，引用用 `../media/<note_id>/` 相对路径。
6. 视频笔记保留正文与封面图，**不下载 mp4**；归档内 `*.mp4` 必须为 0。
7. 评论区只保留博主本人评论 + 被博主回复的原评论及博主回复，无关评论丢弃；**不用 `>` 引用块**，角色名保留 `**加粗**`，正文纯文本。
8. front matter 保留全部字段（`note_id/title/type/time/liked/collected/comment/share/tags/source`），互动数只在正文不显示。
9. **不生成 `index.md`、`build_report.md` 或任何汇总文件**；运行时统计只打印到 stdout。

单篇样例（固定）：

```
---
note_id: "<笔记ID>"
title: "示例笔记标题"
type: "normal"
time: 2025-07-01 03:39:00
liked: 21
collected: 12
comment: 13
share: 2
tags: ["示例标签"]
source: "https://www.xiaohongshu.com/explore/..."
---

# 2025-07 示例笔记标题

发布时间：2025-07-01 03:39
[原帖链接](https://www.xiaohongshu.com/explore/...)

（desc 原文，含 #ict[话题]# 等标签，原样保留）

## 图片

![](../media/<笔记ID>/001.webp)

## 评论区（博主相关）

### 问答 1

**提问者（某用户）** · 2025-07-01 15:24

这里放提问者的原话（逐字保留）...

**博主（博主名）** · 2025-07-01 21:48

这里放博主的回答原话（逐字保留）...
```

## 目录结构（固定）

```
<OUT_DIR>/
  notes/YYYY-MM 标题.md    # 一篇一文件，H1 与文件名同名
  media/<note_id>/*.webp   # 本地图片
  data.jsonl               # 去重后的笔记结构化数据（真源）
  data.raw.json            # 全部原始笔记行
  comments.raw.json        # 全部原始评论行
```

无 `raw/` 月卷、无 `index.md`、无 `build_report.md`。

## 验收

- 单篇文件数 == 去重笔记数 == 主页公开笔记数（允许 ±1~2 条差异；注意列表可能返回重复 ID，按 note_id 去重后才是真实数）。
- 归档内 `*.mp4` == 0；**无 `index.md` / `build_report.md` / 月卷 / 旧 `notes/<note_id>.md` 残留**。
- 抽检：H1 带月份前缀、发布时间行干净、链接在时间下、desc 标签保留、问答无 `>`。
- 脚本 stdout 里博主评论数 > 0；全程账号无验证码 / 功能受限。

## 合规边界

只采公开可见内容；不破解或伪造 x-s / xsec_token、不绕过验证码与风控、不换 IP 池、不高频并发。用途限定个人学习 / 存档，不商用、不转售、不公开再分发原文（版权归作者）；遵守平台条款与 robots。账号风险自担，建议小号。登录 / 验证码一律人工，不代填。

## 踩坑清单

1. **Chrome 136+ / 157 新开关**：`chrome://inspect` 的「Allow remote debugging」只暴露 `ws://localhost:9222/devtools/browser`，`/json/version` 返回 404（Chromium issue 495858087）。MediaCrawler 的 `CDP_CONNECT_EXISTING=True` 已用该 ws 端点，无需改代码；连接现有浏览器时不会关闭用户 Chrome。
2. **代理变量**：环境里 NO_PROXY 含 `[::1]` 会让 httpx 抛 `Invalid port: ':1]'`，登录态检查误判为未登录 → 去点二维码超时。运行前必须 unset 全部代理变量（含小写）。清掉后直连小红书返回 200。
3. **博主身份**：见上，靠 creator_hash 反查，不改上游源码；昵称已脱敏（如 `某***者`）。
4. media 链接（xhscdn）有时效，采集后尽快转换；xsec_token 有时效，链接过期要重新从主页复制。
5. 开源版无断点续爬；按批跑并用 note_id 去重续跑。
6. 中间缓存会下载 mp4（`--get_media` 是整体开关），转换脚本只把图片复制进归档；跑完可删 `<WORK_DIR>/xhs/media/*/*.mp4`。
7. MSYS bash 中文 stdout 可能乱码，写出的文件是正常 UTF-8；建议 PowerShell / CMD 或 `PYTHONIOENCODING=utf-8`。
8. 小红书列表分页可能**重复返回同一 note_id**（某次实战：111 行里 110 个唯一 ID，是重复不是漏抓），去重后再对数量，别误报缺篇。

## 改动记录

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-11-13 | 初版：全量归档流程沉淀成 skill | 首次实战 |
| 2026-11-13 | 格式整改：拆单篇文件、去卷首/互动数/补标签/引用块/「图片（本地）」、原帖链接上移 | 逐条确认 |
| 2026-11-13 | 删除 index.md / build_report.md，脚本不再生成 | 精简产物 |
| 2026-11-13 | 查明「差的 1 篇」是列表重复 ID，去重后即全部唯一笔记 | 复核 jsonl 与日志 |
| 2026-11-13 | 固化 9 条格式规则；输出目录改为 --out 可配置 | 确认 |
