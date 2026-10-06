#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""作业文件批量整理小脚本 —— PR1：需求1 扫描与列出

用法：
    python organizer.py scan <文件夹> [--ext pdf docx]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

JOURNAL_NAME = ".organizer_journal.json"   # 操作日志（后续 PR 会用到）
REPORT_PREFIX = "整理报告"


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


def main():
    ap = argparse.ArgumentParser(description="作业文件批量整理小脚本")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("scan", help="扫描文件夹并列出文件（需求1）")
    p.add_argument("folder", help="要整理的文件夹路径")
    p.add_argument("--ext", nargs="*", default=[],
                   help="按扩展名过滤，如 --ext pdf docx")
    p.set_defaults(func=cmd_scan)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
