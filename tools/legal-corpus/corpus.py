"""法规采集、转换和知识库写入的命令行入口。"""

import argparse
import json
import os
import sys
import tomllib
from pathlib import Path
from uuid import UUID

import httpx
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from collect import TemporarySourceError, collect
from convert import convert_batch
from ingest import ingest_batch


def _parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="保存法规原件和清单")
    commands = parser.add_subparsers(dest="command", required=True)

    gather = commands.add_parser("collect", help="采集清单中的公开法规")
    gather.add_argument("--source", type=Path, default=Path(__file__).with_name("sources.toml"))
    gather.add_argument("--max-pages", type=int, default=1, help="每个栏目最多采集页数")
    gather.add_argument("--max-items", type=int, default=5)
    gather.add_argument("--doc-type", help="只采集配置中指定文种的栏目")
    gather.add_argument("--refresh", action="store_true", help="重新下载并检查正文或元数据变化")
    gather.add_argument("--only-id")

    convert = commands.add_parser("convert", help="用 Docling 转换本地原件")
    convert.add_argument("--format", choices=("html", "docx", "pdf"), default="html")
    convert.add_argument("--models", type=Path, help="本地 Docling 模型目录")
    convert.add_argument("--only-id")

    ingest = commands.add_parser("ingest", help="创建或修订知识库文档")
    ingest.add_argument("--kb-id", required=True, help="目标知识库的字符串 ID")
    ingest.add_argument("--only-id")
    return parser


def main():
    """运行一个阶段。返回 1 表示有失败条目，可按来源 ID 补做。"""
    args = _parser().parse_args()
    try:
        if args.command == "collect":
            with args.source.open("rb") as stream:
                source = tomllib.load(stream)
            if args.doc_type:
                sections = [
                    section for section in source.get("sections", []) if section["doc_type"] == args.doc_type
                ]
                if not sections:
                    raise ValueError("来源配置没有对应文种")
                source["sections"] = sections
            with sync_playwright() as playwright, playwright.chromium.launch() as browser:
                report = collect(
                    browser,
                    source,
                    args.out,
                    max_pages=args.max_pages,
                    max_items=args.max_items,
                    only_id=args.only_id,
                    refresh=args.refresh,
                )
            print(json.dumps(report["counts"], ensure_ascii=False))
            return int(report["counts"]["failed"] > 0)

        if args.command == "convert":
            results = convert_batch(args.out, fmt=args.format, models=args.models, only_id=args.only_id)
        else:
            api = os.environ.get("LEGAL_CORPUS_KB_URL", "")
            token = os.environ.get("LEGAL_CORPUS_KB_TOKEN", "")
            if not api or not token:
                raise ValueError("需要 LEGAL_CORPUS_KB_URL 和 LEGAL_CORPUS_KB_TOKEN")
            try:
                kb_id = str(UUID(args.kb_id))
            except ValueError as exc:
                raise ValueError("目标知识库 ID 必须是 UUID") from exc
            results = ingest_batch(args.out, api=api, token=token, kb_id=kb_id, only_id=args.only_id)
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return int(not results or any(row["status"] == "failed" for row in results))
    except (OSError, ValueError, httpx.HTTPError, PlaywrightError, TemporarySourceError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
