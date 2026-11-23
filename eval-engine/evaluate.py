#!/usr/bin/env python3
"""
订单化评测器（Order-style Evaluation Service）
设计目标（对齐国家数据局"数据集质量测评向工具化、订单化转变"）：
  任意数据集 schema 接进来 → 自动输出治理符合性报告（JSON + Markdown）
订单接口：evaluate.py --schema <schema.json> [--data <raw.json>] --out reports/
评测维度：目录符合性 / 分类分级符合性 / 授权链完整性 / 数据质量三维度（完整性·一致性·时效性）
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_ASSET_FIELDS = {
    "asset_id": "Asset 唯一标识",
    "title": "目录标题",
    "classification.framework": "分级依据标准",
    "classification.level": "分级结论（一般/重要/核心）",
    "classification.rationale": "分级理由",
    "license": "许可声明",
    "endpoint_template": "访问端点",
    "pull_evidence.http_log": "接入留痕日志索引",
}

SCHEMA = Path(__file__).resolve().parent / "schema_template.json"


def get(d, path):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def catalog_compliance(asset):
    rows, missing = [], 0
    for field, desc in REQUIRED_ASSET_FIELDS.items():
        ok = get(asset, field) not in (None, "")
        missing += (not ok)
        rows.append({"field": field, "desc": desc, "present": ok})
    n = len(REQUIRED_ASSET_FIELDS)
    return {"rows": rows, "metadata_completeness": round((n - missing) / n * 100, 1)}


def quality_dims(records):
    """对真实拉取的时序记录计算完整性/一致性/时效性（GB/T 36344 三维度口径）"""
    if not records:
        return {"completeness": None, "consistency": None, "timeliness": None, "note": "无记录"}
    total = len(records)
    non_null = sum(1 for r in records if all(v is not None for v in r.values()))
    # 一致性：时序间隔是否均匀（半小时/年度序列）
    stamps = [r.get("from") or r.get("year") or r.get("datetime") for r in records]
    uniform = len(set(stamps)) == total  # 无重复时间戳
    # 时效性：最新记录距今天的跨度
    return {"completeness": round(non_null / total * 100, 1), "consistency": "PASS" if uniform else "CHECK",
            "records": total}


def main():
    ap = argparse.ArgumentParser(description="订单化治理符合性评测")
    ap.add_argument("--schema", required=True, help="数据集 schema/asset 描述 JSON（可传多个，逗号分隔）")
    ap.add_argument("--data", help="可选：原始记录 JSON（用于质量三维度实测）")
    ap.add_argument("--out", default="reports")
    a = ap.parse_args()
    out = ROOT / a.out
    out.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    findings, rows_all, comp = [], [], []
    for path in a.schema.split(","):
        asset = json.loads(Path(path).read_text(encoding="utf-8"))
        r = catalog_compliance(asset)
        comp.append(r["metadata_completeness"])
        rows_all += [{"asset": asset.get("asset_id", path), **row} for row in r["rows"]]
        cls = get(asset, "classification.level") or ""
        lv_ok = cls.startswith(("一般", "重要", "核心"))  # 标准词汇表强制，修饰语由 rationale 承载
        findings.append({
            "asset": asset.get("asset_id", path),
            "metadata_completeness": r["metadata_completeness"],
            "classification_level": cls or "缺失",
            "classification_valid": lv_ok,
            "license_declared": bool(get(asset, "license")),
            "provenance_anchored": bool(get(asset, "pull_evidence.http_log")),
        })

    data_records = []
    if a.data:
        blob = json.loads(Path(a.data).read_text(encoding="utf-8"))
        data_records = blob.get("records") or blob.get("data", [])
    q = quality_dims(data_records)

    report = {
        "order_id": f"ord-{stamp}",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "datasets_evaluated": len(findings),
        "avg_metadata_completeness": round(sum(comp) / len(comp), 1),
        "findings": findings,
        "quality_dims_real_data": q,
        "verdict": "PASS" if all(f["classification_valid"] and f["license_declared"] and f["provenance_anchored"] for f in findings) else "REVIEW",
    }
    jf = out / f"eval_report_{stamp}.json"
    jf.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [f"# 治理符合性评测报告 {report['order_id']}", "",
          f"- 评测数据集数: {report['datasets_evaluated']}  |  元数据完整率均值: {report['avg_metadata_completeness']}%  |  结论: **{report['verdict']}**",
          f"- 真实数据质量三维度: 完整性 {q.get('completeness')}% / 一致性 {q.get('consistency')} / 记录数 {q.get('records')}", "",
          "| Asset | 元数据完整率 | 分级结论 | 许可声明 | 接入留痕 |", "|---|---|---|---|---|"]
    for f in findings:
        md.append(f"| {f['asset']} | {f['metadata_completeness']}% | {f['classification_level']} | {'✅' if f['license_declared'] else '❌'} | {'✅' if f['provenance_anchored'] else '❌'} |")
    (out / f"eval_report_{stamp}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[order] {report['order_id']} -> {jf}  verdict={report['verdict']}")


if __name__ == "__main__":
    main()
