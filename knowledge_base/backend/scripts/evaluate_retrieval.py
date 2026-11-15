"""用管理员检索测试接口对比向量、混合及重排结果。"""

import argparse
import json
import math
import os
from collections import Counter
from pathlib import Path
from statistics import mean
from time import perf_counter
from urllib.parse import quote

import httpx

STRATEGIES = ("vector", "hybrid", "reranked")
DEFAULT_CASES = Path(__file__).with_name("retrieval_cases.json")


def _label(item):
    metadata = item.get("metadata") or {}
    return metadata.get("law_name") or item["title"], metadata.get("article_no")


def _search(client, path, case, strategy, top_k, *, include_abolished=False):
    response = client.post(
        path,
        json={
            "query": case["query"],
            "strategy": strategy,
            "top_k": top_k,
            "diagnostics": True,
            "include_abolished": include_abolished,
        },
    ).json()
    if response["code"] != 0:
        raise RuntimeError(f"{case['name']} / {strategy}: 检索业务码 {response['code']}")
    return response["data"]


def _source_is(result, source):
    actual = (result.get("metadata") or {}).get("source_url")
    return isinstance(actual, str) and actual.rstrip("/") == source.rstrip("/")


def evaluate(client, path, cases, top_k, repeats):
    """逐条记录首个命中、召回率、各路状态和 P95，保留负例便于复查。"""
    results = {}
    for strategy in STRATEGIES:
        measured, rows = [], []
        for case in cases:
            for _ in range(repeats):
                start = perf_counter()
                data = _search(client, path, case, strategy, top_k)
                measured.append((perf_counter() - start) * 1000)
            results_at_k = data["items"]
            diagnosed = data["diagnostics"]
            labels = [_label(result) for result in results_at_k]
            expected = {(item["law_name"], item.get("article_no")) for item in case["relevant"]}
            first = next((index for index, label in enumerate(labels, 1) if label in expected), None)
            row = {
                "case": case["name"],
                "results": [list(label) for label in labels],
                "first_relevant_rank": first,
                "recall": len(expected.intersection(labels)) / len(expected) if expected else None,
                "vector": diagnosed["vector"]["status"],
                "keyword": diagnosed["keyword"]["status"],
                "rerank": diagnosed["rerank"]["status"],
                "no_answer_returns_candidates": bool(labels)
                if not expected and not case.get("excluded_source")
                else None,
            }
            if excluded := case.get("excluded_source"):
                comparison = _search(client, path, case, strategy, top_k, include_abolished=True)
                row["excluded_result_leaked"] = any(_source_is(result, excluded) for result in results_at_k)
                row["excluded_control_seen"] = any(
                    _source_is(result, excluded) for result in comparison["items"]
                )
            rows.append(row)
        relevant = [row for row in rows if row["recall"] is not None]
        measured.sort()
        results[strategy] = {
            "recall_at_k": mean(row["recall"] for row in relevant) if relevant else None,
            "mrr_at_k": mean(
                1 / row["first_relevant_rank"] if row["first_relevant_rank"] else 0 for row in relevant
            )
            if relevant
            else None,
            "p95_ms": round(measured[math.ceil(len(measured) * 0.95) - 1], 2),
            "requests": len(measured),
            "rerank_statuses": dict(Counter(row["rerank"] for row in rows)),
            "cases": rows,
        }
    return {"top_k": top_k, "repeats": repeats, "strategies": results}


def main():
    """从环境读取测试凭证，将评测结果写入 JSON。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="测试知识库 API 的服务地址")
    parser.add_argument("--knowledge-base", required=True, help="包含评测语料的库 ID")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    token = os.environ.get("KB_EVALUATION_TOKEN")
    if not token:
        parser.error("需要通过 KB_EVALUATION_TOKEN 提供管理员令牌")
    if not 1 <= args.top_k <= 20 or args.repeats < 1:
        parser.error("top-k 须在 1–20，repeats 至少为 1")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if not cases:
        parser.error("评测集不能为空")
    with httpx.Client(
        base_url=args.base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30
    ) as client:
        path = f"/api/knowledge-bases/{quote(args.knowledge_base, safe='')}/search"
        result = evaluate(client, path, cases, args.top_k, args.repeats)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
