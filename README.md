# xhs-archive

一个 agent skill：把某个小红书博主的全部公开笔记归档成单篇 Markdown（正文原文 + 本地图片 + 只保留博主本人评论及被博主回复的问答对）。

## 文件

| 文件 | 说明 |
|---|---|
| `SKILL.md` | 触发条件、参数、采集/转换流程、9 条格式规则、踩坑清单 |
| `scripts/build_archive.py` | 转换脚本，仅 Python 标准库，幂等，可从 jsonl 重建全部 Markdown |

## 安装

把本目录放到 `~/.agents/skills/xhs-archive/`（Windows：`C:/Users/<用户名>/.agents/skills/xhs-archive/`）。skill catalog 会自动发现。

## 快速开始

1. 前置：Python 3.12 venv + MediaCrawler（见 `SKILL.md`「前置环境」）、Chrome 远程调试开关、人工登录小红书。
2. 采集：按 `SKILL.md`「采集」跑 MediaCrawler 的 creator 模式，产出 jsonl 与媒体缓存。
3. 转换：

```
python scripts/build_archive.py \
  --input "<WORK_DIR>/xhs/jsonl" --comments "<WORK_DIR>/xhs/jsonl" \
  --out "<OUT_DIR>" --name "<博主名>" \
  --source-url "<主页链接>" --media-root "<WORK_DIR>"
```

`--author-hash` 留空时会自动从主页链接的 user_id 推算，无需硬编码任何博主专属值。

## 输出格式

见 `SKILL.md`「最终格式规格」：一篇一个 md、H1 带月份前缀、发布时间下紧跟原帖链接、desc 原文原样保留、图片本地化、评论区只留博主相关问答且不用 `>` 引用块、不下载视频、不生成 `index.md` / `build_report.md` / 月卷。

## 合规

只采公开可见内容；低频、不绕过验证码与风控、不商用、不转售原文；账号风险自担；登录与验证码一律人工完成。使用前请自行评估目标平台服务条款与内容版权。

## 踩坑

见 `SKILL.md`「踩坑清单」：Chrome 136+ 新远程调试开关只暴露 ws 端点、代理变量中畸形 NO_PROXY 会让 httpx 抛错、教学版 user_id 匿名化需正向算哈希反查博主、媒体链接有时效等。