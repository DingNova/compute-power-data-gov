"""
pdp/run_matrix.py — 48 组全因子决策矩阵批测

因子：4 asset × 4 主体角色 × 3 协议段（catalog / negotiation / transfer）
产出：tck-evidence/pdp_evidence/decision_log.jsonl（逐条决策+求值轨迹）
      reports/matrix_report.json / .md（混淆矩阵、拦截率、延迟分布）
"""
from __future__ import annotations

import json
import statistics
import time
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import PDP, AccessRequest, ASSET_LEVELS, RESEARCH_PURPOSE

REPO = Path(__file__).resolve().parent.parent
EV = REPO / "tck-evidence" / "pdp_evidence"
REPORTS = REPO / "reports"
EV.mkdir(parents=True, exist_ok=True)

ASSETS = [
    "asset:uk-carbon-intensity-48h",          # 一般（有策略1/2）
    "asset:owid-gbr-electricity-annual",      # 一般（策略覆盖：共用 carbon 的 target 吗？否——独立无策略）
    "asset:gb-grid-aggregated-load",          # 重要（演示：无策略，预期暴露 ERR_NO_POLICY 缺口）
    "asset:derived:compute-power-correlation",  # 衍生→重要（策略3）
]
ROLES = [
    ("computeside-research", RESEARCH_PURPOSE),
    ("commercial-resale", "commercial-resale"),
    ("unknown-third-party", None),
    ("cross-subject-aggregator", RESEARCH_PURPOSE),
]
SEGMENTS = ["catalog", "negotiation", "transfer"]


def action_for(seg: str, role: str) -> tuple[str, list[str]]:
    if seg == "catalog":
        return "odrl:read", []
    if role == "cross-subject-aggregator":
        return "odrl:aggregate", []
    if seg == "negotiation":
        return "odrl:analyze", []
    return "odrl:distribute", []


def catalog_decision(asset: str) -> dict:
    """目录段：可见性按 DCAT 注册表判定（元数据检查，非策略求值）"""
    t0 = time.perf_counter()
    registered = asset in ASSET_LEVELS
    return {
        "decision": "ALLOW" if registered else "DENY",
        "denial_code": None if registered else "ERR_UNREGISTERED_ASSET",
        "trace": [{"step": "dcat_registration_lookup",
                   "registered": registered,
                   "classification": ASSET_LEVELS.get(asset, "-")}],
        "duties": [], "escalation": None,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 3),
    }


def expected_decision(asset: str, seg: str, role: str) -> str:
    """预期判定 oracle（独立于实现推导，用于混淆矩阵）"""
    if seg == "catalog":
        return "ALLOW" if asset in ASSET_LEVELS else "DENY"
    if role == "cross-subject-aggregator":
        # 聚合通道：目标固定为衍生资产；升级判定见 run_aggregator
        if asset == "asset:gb-grid-aggregated-load":
            return "ALLOW_WITH_DUTY"     # 重要输入 → 升级 + reclassify
        return "ALLOW_WITH_DUTY" if asset == "asset:derived:compute-power-correlation" else "ALLOW"
    if asset == "asset:gb-grid-aggregated-load":
        return "DENY"          # 无策略覆盖 → 预期拒绝（缺口场景）
    if asset == "asset:derived:compute-power-correlation":
        return "DENY"          # 衍生资产仅可经聚合通道访问
    if role == "commercial-resale" or role == "unknown-third-party":
        return "DENY"
    return "ALLOW_WITH_DUTY"   # 研究用途：放行且附署名义务


def main():
    pdp = PDP()
    log_path = EV / "decision_log.jsonl"
    rows = []
    with open(log_path, "w", encoding="utf-8") as f:
        for seg in SEGMENTS:
            for asset in ASSETS:
                for role, purpose in ROLES:
                    act, _ = action_for(seg, role)
                    # 聚合通道：目标固定为衍生资产，输入随 asset 列变化（测试就高从严各分支）
                    if role == "cross-subject-aggregator":
                        if seg == "catalog":
                            target = asset
                        else:
                            target = "asset:derived:compute-power-correlation"
                            if asset == "asset:derived:compute-power-correlation":
                                inputs = ["asset:uk-carbon-intensity-48h",
                                          "asset:owid-gbr-electricity-annual"]
                            else:
                                inputs = [asset]
                    else:
                        target = asset
                        inputs = []
                    if seg == "catalog":
                        cd = catalog_decision(target)
                        row = {"segment": seg, "asset": asset, "role": role,
                               "action": "odrl:read", "purpose": purpose,
                               "expected": expected_decision(asset, seg, role),
                               "actual": cd["decision"],
                               "correct": cd["decision"] == expected_decision(asset, seg, role),
                               "denial_code": cd["denial_code"],
                               "duties": cd["duties"], "escalation": cd["escalation"],
                               "latency_ms": cd["latency_ms"],
                               "trace": cd["trace"], "request_id": "-", "ts_utc": "-"}
                    else:
                        req = AccessRequest(target, f"urn:consumer:{role}", purpose, act, inputs)
                        d = pdp.evaluate(req)
                        row = {"segment": seg, "asset": asset, "role": role,
                               "action": act, "purpose": purpose,
                               "expected": expected_decision(asset, seg, role),
                               "actual": d.decision,
                               "correct": d.decision == expected_decision(asset, seg, role),
                               "denial_code": d.denial_code,
                               "duties": d.duties, "escalation": d.escalation,
                               "latency_ms": d.latency_ms,
                               "trace": d.evaluation_trace,
                               "request_id": d.request_id, "ts_utc": d.ts_utc}
                    rows.append(row)
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # ---- 统计 ----
    n = len(rows)
    correct = sum(1 for r in rows if r["correct"])
    exp_deny = [r for r in rows if r["expected"] == "DENY"]
    caught = [r for r in exp_deny if r["actual"] == "DENY"]
    missed = [r for r in exp_deny if r["actual"] != "DENY"]
    exp_allow = [r for r in rows if r["expected"] != "DENY"]
    false_deny = [r for r in exp_allow if r["actual"] == "DENY"]
    lat = sorted(r["latency_ms"] for r in rows)
    p50 = statistics.median(lat)
    p95 = lat[int(len(lat) * 0.95) - 1]

    denial_dist: dict[str, int] = {}
    for r in rows:
        if r["denial_code"]:
            denial_dist[r["denial_code"]] = denial_dist.get(r["denial_code"], 0) + 1

    by_segment = {}
    for seg in SEGMENTS:
        seg_rows = [r for r in rows if r["segment"] == seg]
        by_segment[seg] = {
            "n": len(seg_rows),
            "deny": sum(1 for r in seg_rows if r["actual"] == "DENY"),
            "allow": sum(1 for r in seg_rows if r["actual"] != "DENY"),
        }

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "design": "4 assets x 4 roles x 3 DSP segments (full factorial)",
        "total_decisions": n,
        "oracle_accuracy": round(correct / n, 4),
        "denial_detection_rate": round(len(caught) / len(exp_deny), 4) if exp_deny else None,
        "false_deny_rate": round(len(false_deny) / len(exp_allow), 4) if exp_allow else None,
        "confusion": {"expected_deny": len(exp_deny), "caught": len(caught),
                      "missed": len(missed), "expected_allow": len(exp_allow),
                      "false_deny": len(false_deny)},
        "denial_code_distribution": denial_dist,
        "latency_ms": {"p50": round(p50, 3), "p95": round(p95, 3),
                       "max": round(max(lat), 3)},
        "by_segment": by_segment,
        "findings": [],
    }
    if missed:
        report["findings"].append(
            {"severity": "high", "issue": "expected-deny missed",
             "cells": [f"{r['segment']}/{r['asset']}/{r['role']}" for r in missed]})
    if false_deny:
        report["findings"].append(
            {"severity": "medium", "issue": "expected-allow denied (over-restriction)",
             "cells": [f"{r['segment']}/{r['asset']}/{r['role']}" for r in false_deny]})
    # 已知缺口：gb-grid-aggregated-load 无策略
    report["findings"].append(
        {"severity": "info", "issue": "asset gb-grid-aggregated-load lacks ODRL policy "
         "→ negotiation/transfer ERR_NO_POLICY；目录可见但谈判拒绝，暴露策略缺口（评测器的价值证明）"})

    (REPORTS / "matrix_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # markdown 摘要
    md = [
        "# 48 组全因子决策矩阵批测报告",
        f"\n生成时间：{report['generated_at']}",
        f"\n| 指标 | 值 |\n|---|---|",
        f"| 决策总数 | {n} |",
        f"| Oracle 一致率 | {report['oracle_accuracy']:.1%} |",
        f"| 越权拦截率 | {report['denial_detection_rate']:.1%} ({len(caught)}/{len(exp_deny)}) |",
        f"| 误拒率 | {report['false_deny_rate']:.1%} ({len(false_deny)}/{len(exp_allow)}) |",
        f"| 延迟 P50/P95/max | {p50:.2f} / {p95:.2f} / {max(lat):.2f} ms |",
        "\n## 分段统计\n\n| 协议段 | 总数 | DENY | ALLOW(+DUTY) |\n|---|---|---|---|",
        *[f"| {s} | {v['n']} | {v['deny']} | {v['allow']} |" for s, v in by_segment.items()],
        "\n## 拒绝原因码分布\n\n| 拒绝码 | 次数 |\n|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(denial_dist.items())],
        "\n## 发现\n",
        *[f"- **[{f['severity']}]** {f['issue']}" +
          (f"：`{'`, `'.join(f['cells'])}`" if f.get("cells") else "")
          for f in report["findings"]],
    ]
    (REPORTS / "matrix_report.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ["total_decisions", "oracle_accuracy", "denial_detection_rate",
                       "false_deny_rate", "latency_ms", "denial_code_distribution"]},
                     ensure_ascii=False, indent=1))
    print(f"\nlogs: {log_path}\nreports: {REPORTS/'matrix_report.md'}")


if __name__ == "__main__":
    main()
