#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作业文件批量整理小脚本（完整版）

子命令与需求对应：
    scan     需求1  扫描文件夹，列出文件大小与修改时间，支持扩展名过滤
    rename   需求2  批量重命名：先打印预览，确认后才执行；重名冲突一律跳过
    archive  需求3  按学期/扩展名归档到子文件夹，并生成整理报告
    undo     需求3  撤销上一次 rename / archive 操作

无第三方依赖，Python 3.8+ 可运行。

用法示例：
    python organizer.py scan ./待整理 --ext pdf docx
    python organizer.py rename ./待整理 --apply
    python organizer.py archive ./待整理 --by semester --apply
    python organizer.py undo ./待整理
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

JOURNAL_NAME = ".organizer_journal.json"   # 操作日志：记录每次实际改动，undo 的依据
REPORT_PREFIX = "整理报告"
UNCLASSIFIED = "未分类"
SEMESTER_RE = re.compile(r"(20\d{2})\s*([春夏秋冬])")


def human_size(n):
    """字节数 -> 可读大小（KB/MB...）"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return ("%.0f %s" if unit == "B" else "%.1f %s") % (n, unit)
        n /= 1024
    return "%.1f TB" % n


def normalize_exts(raw):
    """['pdf', '.PDF'] -> ['.pdf']，统一成小写带点格式"""
    out = []
    for e in raw or []:
        e = e.strip().lower()
        if not e:
            continue
        if not e.startswith("."):
            e = "." + e
        if e not in out:
            out.append(e)
    return out


def list_files(folder, exts=None):
    """列出文件夹顶层的普通文件（跳过操作日志和历史报告），按文件名排序。"""
    files = []
    for p in sorted(folder.iterdir(), key=lambda x: x.name):
        if not p.is_file():
            continue
        if p.name == JOURNAL_NAME or p.name.startswith(REPORT_PREFIX):
            continue
        if exts and p.suffix.lower() not in exts:
            continue
        files.append(p)
    return files


# ---------- 操作日志（支撑 undo） ----------

def load_journal(folder):
    p = folder / JOURNAL_NAME
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            print("[警告] 操作日志损坏，将重新开始记录", file=sys.stderr)
    return {"history": []}


def save_journal(folder, journal):
    (folder / JOURNAL_NAME).write_text(
        json.dumps(journal, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def record_batch(folder, action, operations, skipped):
    """把一次实际执行的操作整体记入日志，undo 时按批还原。"""
    journal = load_journal(folder)
    journal["history"].append({
        "time": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "operations": operations,   # [{"src": 绝对路径, "dst": 绝对路径}]
        "skipped": skipped,         # [{"file": ..., "reason": ...}]
    })
    save_journal(folder, journal)


def confirm(prompt="确认执行？(y/N): "):
    try:
        ans = input(prompt).strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


# ---------- 需求1：扫描与列出 ----------

def cmd_scan(args):
    """需求1：扫描指定文件夹，列出所有文件的大小和修改时间，支持扩展名过滤。"""
    folder = Path(args.folder)
    if not folder.is_dir():
        sys.exit("[错误] 文件夹不存在: %s" % folder)

    exts = normalize_exts(args.ext)
    files = list_files(folder, exts or None)

    print("文件名\t大小\t修改时间")
    print("-" * 60)
    total = 0
    for p in files:
        st = p.stat()
        total += st.st_size
        mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        print("%s\t%s\t%s" % (p.name, human_size(st.st_size), mtime))
    print("-" * 60)

    summary = "共 %d 个文件，合计 %s" % (len(files), human_size(total))
    if exts:
        summary += "（扩展名过滤：%s）" % "、".join(exts)
    print(summary)


# ---------- 需求2：批量重命名 ----------

def cmd_rename(args):
    """需求2：按规则批量重命名。先打印预览，确认后才真的改；重名冲突一律跳过。"""
    folder = Path(args.folder)
    if not folder.is_dir():
        sys.exit("[错误] 文件夹不存在: %s" % folder)

    exts = normalize_exts(args.ext)
    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    files = list_files(folder, exts or None)

    plan, skipped, taken = [], [], set()
    for p in files:
        parts = p.stem.split("_")
        if len(parts) != len(fields):
            skipped.append({"file": p.name,
                            "reason": "文件名按下划线拆出 %d 段，与字段数 %d 不匹配"
                                      % (len(parts), len(fields))})
            continue
        ctx = dict(zip(fields, parts))
        try:
            new_stem = args.template.format(**ctx)
        except (KeyError, IndexError) as e:
            skipped.append({"file": p.name, "reason": "模板字段无法解析: %s" % e})
            continue
        new_name = new_stem + p.suffix
        if new_name == p.name:
            skipped.append({"file": p.name, "reason": "新文件名与原来相同"})
            continue
        if new_name.casefold() in taken or (folder / new_name).exists():
            skipped.append({"file": p.name,
                            "reason": "目标 \"%s\" 已存在，为避免覆盖跳过" % new_name})
            continue
        taken.add(new_name.casefold())
        plan.append((p, folder / new_name))

    print("== 重命名预览 ==")
    for src, dst in plan:
        print("  %s  ->  %s" % (src.name, dst.name))
    print("待重命名 %d 个，跳过 %d 个" % (len(plan), len(skipped)))
    for s in skipped:
        print("  [跳过] %s：%s" % (s["file"], s["reason"]))

    if not plan:
        return
    if not args.apply:
        print("\n以上仅为预览，未做任何修改。确认无误后加 --apply 执行。")
        return
    if not args.yes and not confirm():
        print("已取消，未做任何修改。")
        return

    operations = []
    for src, dst in plan:
        try:
            src.rename(dst)
        except OSError as e:
            print("  [失败] %s：%s（文件可能被其他程序占用）" % (src.name, e))
            continue
        operations.append({"src": str(src.resolve()), "dst": str(dst.resolve())})
    record_batch(folder, "rename", operations, skipped)
    print("完成：已重命名 %d 个文件，可用 undo 撤销本次。" % len(operations))


# ---------- 需求3：归档、报告与撤销 ----------

def semester_of(stem):
    """从文件名里识别学期，如 2023秋 / 2024春；识别不了返回 None。"""
    m = SEMESTER_RE.search(stem)
    if not m:
        return None
    return m.group(1) + m.group(2)


def cmd_archive(args):
    """需求3：把文件移动到子文件夹（按学期或扩展名），并生成整理报告。"""
    folder = Path(args.folder)
    if not folder.is_dir():
        sys.exit("[错误] 文件夹不存在: %s" % folder)

    exts = normalize_exts(args.ext)
    files = list_files(folder, exts or None)

    plan, skipped = [], []
    for p in files:
        if args.by == "ext":
            sub = p.suffix.lstrip(".").lower() or "无扩展名"
        else:  # semester
            sub = semester_of(p.stem) or UNCLASSIFIED
        target = folder / sub / p.name
        if target.exists():
            skipped.append({"file": p.name,
                            "reason": "子文件夹 %s 中已有同名文件，为避免覆盖跳过" % sub})
            continue
        plan.append((p, target))

    print("== 归档预览（按%s）==" % ("扩展名" if args.by == "ext" else "学期"))
    for src, dst in plan:
        print("  %s  ->  %s" % (src.name, dst.relative_to(folder)))
    print("待移动 %d 个，跳过 %d 个" % (len(plan), len(skipped)))
    for s in skipped:
        print("  [跳过] %s：%s" % (s["file"], s["reason"]))

    if not plan:
        return
    if not args.apply:
        print("\n以上仅为预览，未做任何修改。确认无误后加 --apply 执行。")
        return
    if not args.yes and not confirm():
        print("已取消，未做任何修改。")
        return

    operations = []
    for src, dst in plan:
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            src.rename(dst)
        except OSError as e:
            print("  [失败] %s：%s（文件可能被其他程序占用）" % (src.name, e))
            continue
        operations.append({"src": str(src.resolve()), "dst": str(dst.resolve())})
    record_batch(folder, "archive", operations, skipped)

    # 生成整理报告：处理了多少、跳过了多少、为什么跳过
    now = datetime.now()
    report = folder / ("%s_%s.md" % (REPORT_PREFIX, now.strftime("%Y%m%d_%H%M%S")))
    lines = [
        "# 文件整理报告",
        "",
        "- 时间：%s" % now.strftime("%Y-%m-%d %H:%M:%S"),
        "- 模式：按%s归档到子文件夹" % ("扩展名" if args.by == "ext" else "学期"),
        "- 处理：%d 个" % len(operations),
        "- 跳过：%d 个" % len(skipped),
        "",
        "## 明细",
    ]
    for op in operations:
        dst = Path(op["dst"])
        lines.append("- [已移动] %s -> %s/%s" % (Path(op["src"]).name, dst.parent.name, dst.name))
    for s in skipped:
        lines.append("- [跳过] %s —— %s" % (s["file"], s["reason"]))
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("完成：移动 %d 个文件，整理报告已生成：%s" % (len(operations), report.name))
    print("可用 undo 撤销本次归档。")


def cmd_undo(args):
    """需求3：撤销最近一次 rename / archive 操作（依据 .organizer_journal.json）。"""
    folder = Path(args.folder)
    if not folder.is_dir():
        sys.exit("[错误] 文件夹不存在: %s" % folder)

    journal = load_journal(folder)
    history = journal.get("history", [])
    if not history:
        print("没有可撤销的操作。")
        return

    batch = history[-1]
    print("将撤销 %s 的「%s」操作（涉及 %d 个文件的移动）。"
          % (batch["time"], batch["action"], len(batch["operations"])))
    if not args.yes and not confirm("确认撤销？(y/N): "):
        print("已取消。")
        return

    undone, failed = 0, []
    for op in reversed(batch["operations"]):
        dst, src = Path(op["dst"]), Path(op["src"])
        if dst.exists() and not src.exists():
            dst.rename(src)
            undone += 1
        elif src.exists():
            failed.append("%s（原位置已有同名文件，未动）" % dst.name)
        else:
            failed.append("%s（文件不见了，无法还原）" % dst.name)

    history.pop()
    save_journal(folder, journal)
    print("撤销完成：已还原 %d 个文件。" % undone)
    for f in failed:
        print("  [未还原] %s" % f)


def main():
    ap = argparse.ArgumentParser(description="作业文件批量整理小脚本")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="扫描文件夹并列出文件（需求1）")
    p.add_argument("folder", help="要整理的文件夹路径")
    p.add_argument("--ext", nargs="*", default=[],
                   help="按扩展名过滤，如 --ext pdf docx")
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("rename", help="批量重命名（需求2）")
    p.add_argument("folder", help="要整理的文件夹路径")
    p.add_argument("--fields", default="学号,姓名,作业名",
                   help="文件名按下划线拆分后各段的含义，逗号分隔")
    p.add_argument("--template", default="{作业名}_{学号}",
                   help="新文件名模板，如 \"{作业名}_{学号}\"")
    p.add_argument("--ext", nargs="*", default=[],
                   help="按扩展名过滤，如 --ext pdf docx")
    p.add_argument("--apply", action="store_true",
                   help="真正执行改名（不加则只打印预览）")
    p.add_argument("--yes", action="store_true", help="跳过二次确认")
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("archive", help="归档到子文件夹并生成报告（需求3）")
    p.add_argument("folder", help="要整理的文件夹路径")
    p.add_argument("--by", choices=["semester", "ext"], default="semester",
                   help="归档依据：semester=文件名里的学期，ext=扩展名")
    p.add_argument("--ext", nargs="*", default=[],
                   help="按扩展名过滤，如 --ext pdf docx")
    p.add_argument("--apply", action="store_true",
                   help="真正执行移动（不加则只打印预览）")
    p.add_argument("--yes", action="store_true", help="跳过二次确认")
    p.set_defaults(func=cmd_archive)

    p = sub.add_parser("undo", help="撤销上一次 rename/archive（需求3）")
    p.add_argument("folder", help="要整理的文件夹路径")
    p.add_argument("--yes", action="store_true", help="跳过二次确认")
    p.set_defaults(func=cmd_undo)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
