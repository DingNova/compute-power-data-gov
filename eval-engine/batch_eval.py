#!/usr/bin/env python3
"""
订单化评测器扩容批测（n=60，含注入缺陷样本）
目的：把"评测器能逮住缺陷"从 n=2 的个案变成统计结论——
  缺陷检出率（8 类注入缺陷）、误报率（干净样本）、单订单评测耗时分布 P50/P95。
缺陷注入模型：对真实 asset schema 做 8 类受控变异（每类 5 个样本），
  覆盖：许可缺失 / 分级词汇违规 / 分级缺失 / 接入留痕缺失 / 端点缺失 /
        标题缺失 / 理由缺失 / 多缺陷叠加。
判定口径：
  检出 = verdict==REVIEW 或 metadata_completeness<100
  误报 = 干净样本被判定为检出
"""
import json
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate import catalog_compliance, get  # noqa: E402  复用正式评测逻辑

ROOT = Path(__file__).resolve().parent.parent
EV = ROOT / "tck-evidence" / "pdp_evidence"
REPORTS = ROOT / "reports"

REAL_ASSETS = sorted((ROOT / "data" / "raw").glob("*_asset_*.json"))

DEFECTS = {
    "license_missing":      lambda a: {**a, "license": None},
    "cls_bad_vocab":        lambda a: {**a, "classification": {**a["classification"], "level": "公开级（大概是）"}},
    "cls_missing":          lambda a: {**a, "classification": {k: v for k, v in a["classification"].items() if k != "level"}},
    "provenance_missing":   lambda a: {**a, "pull_evidence": {k: v for k, v in a.get("pull_evidence", {}).items() if k != "http_log"}},
    "endpoint_missing":     lambda a: {**a, "endpoint_template": None},
    "title_missing":        lambda a: {**a, "title": None},
    "rationale_missing":    lambda a: {**a, "classification": {**a["classification"], "rationale": None}},
    "combo_multi_defect":   lambda a: DEFECTS["license_missing"](DEFECTS["endpoint_missing"](a)),
}


def eval_one(asset: dict) -> dict:
    """单订单评测（口径与 evaluate.py verdict 完全一致）"""
    t0 = time.perf_counter()
    r = catalog_compliance(asset)
    cls = get(asset, "classification.level") or ""
    verdict = "PASS" if (cls.startswith(("一般", "重要", "核心"))
                         and bool(get(asset, "license"))
                         and bool(get(asset, "pull_evidence.http_log"))) else "REVIEW"
    return {
        "verdict": verdict,
        "completeness": r["metadata_completeness"],
        "latency_ms": round((time.perf_counter() - t0) * 1000, 3),
    }


def main():
    rng = random.Random(20261124)  # 固定种子：批测完全可复现
    base_assets = [json.loads(p.read_text(encoding="utf-8")) for p in REAL_ASSETS]

    cases = []  # (case_id, defect_type, asset, expected_detect)
    n = 0
    for defect, mutate in DEFECTS.items():
        for base in rng.sample(base_assets * 3, 5):  # 每类缺陷 5 样本，两个真实资产轮换
            n += 1
            cases.append((f"case-{n:03d}", defect, mutate(base), True))
    for i in range(20):  # 20 个干净样本（真实资产原样 + 深拷贝扰动无关字段如 note）
        n += 1
        base = dict(rng.choice(base_assets))
        base["note"] = f"clean-sample-{i}"
        cases.append((f"case-{n:03d}", "clean", base, False))

    rows, lat = [], []
    tp = fn = tn = fp = 0
    per_defect = {}
    for cid, dtype, asset, exp in cases:
        r = eval_one(asset)
        detected = r["verdict"] == "REVIEW" or r["completeness"] < 100
        correct = detected == exp
        lat.append(r["latency_ms"])
        d = per_defect.setdefault(dtype, {"n": 0, "detected": 0})
        d["n"] += 1
        d["detected"] += detected
        if exp and detected:
            tp += 1
        elif exp and not detected:
            fn += 1
        elif not exp and not detected:
            tn += 1
        else:
            fp += 1
        rows.append({"case_id": cid, "defect_type": dtype, "asset": asset.get("asset_id"),
                     "expected_detect": exp, "detected": detected, "correct": correct,
                     "verdict": r["verdict"], "completeness": r["completeness"],
                     "latency_ms": r["latency_ms"]})

    lat.sort()
    p50 = lat[len(lat) // 2]
    p95 = lat[int(len(lat) * 0.95) - 1]
    lat.sort()
    report = {
        "batch_id": f"batch-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "seed": 20261124,
        "total_orders": len(cases),
        "clean_orders": tn + fp,
        "defective_orders": tp + fn,
        "defect_detection_rate": round(tp / (tp + fn) * 100, 1),
        "false_positive_rate": round(fp / (tn + fp) * 100, 1),
        "accuracy": round((tp + tn) / len(cases) * 100, 1),
        "latency_ms_p50": p50, "latency_ms_p95": p95,
        "per_defect_type": per_defect,
    }

    EV.mkdir(parents=True, exist_ok=True)
    (EV / "eval_batch_log.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "eval_batch_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# 订单化评测器扩容批测报告", "",
          f"- 批次: `{report['batch_id']}`（种子 {report['seed']}，完全可复现）",
          f"- 订单总数 **{report['total_orders']}**（干净 {report['clean_orders']} / 注入缺陷 {report['defective_orders']}，8 类缺陷 × 5 样本）",
          f"- **缺陷检出率 {report['defect_detection_rate']}%** ｜ **误报率 {report['false_positive_rate']}%** ｜ 准确率 {report['accuracy']}%",
          f"- 单订单评测耗时 P50 {p50} ms / P95 {p95} ms", "",
          "| 缺陷类型 | 样本数 | 检出数 | 检出率 |", "|---|---|---|---|"]
    for k, v in per_defect.items():
        md.append(f"| {k} | {v['n']} | {v['detected']} | {round(v['detected']/v['n']*100)}% |")
    (REPORTS / "eval_batch_report.md").write_text("\n".join(md), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
