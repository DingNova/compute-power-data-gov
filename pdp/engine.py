"""
pdp/engine.py — ODRL 策略决策点（Policy Decision Point）

真实加载 policies/odrl/*.jsonld，对访问请求逐条约束求值，输出决策日志。
设计参照 XACML PDP 角色：PAP=本仓库 policies/ 目录；本模块=PDP；
调用方（连接器/DSP 消息层）=PEP。

求值语义（对齐 ODRL 2.0 core vocabulary + 本项目 tdg 扩展）：
1. 命中策略：按 target 匹配 Offer/Agreement
2. prohibition 命中 constraint → DENY（拒绝优先）
3. permission 全部 constraint 满足 → ALLOW（如有 duty 则附带义务）
4. 自定义扩展 tdg:aggregateEscalation：聚合衍生请求按"就高从严"判定，
   结果等级 ≥ important 时要求 duty tdg:reclassify
5. 无策略覆盖 target → PERMIT_ONLY_CATALOG（目录可见，谈判需补策略）
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
POLICY_DIR = REPO / "policies" / "odrl"

# 分类分级表（policies/catalog/classification-mapping.md 的机器可读版）
ASSET_LEVELS = {
    "asset:uk-carbon-intensity-48h": "一般",
    "asset:owid-gbr-electricity-annual": "一般",
    "asset:gb-grid-aggregated-load": "重要",        # 演示：多主体负荷聚合（重要级）
    "asset:derived:compute-power-correlation": "重要",
}
# 资产所属主体（跨主体聚合判定用）
ASSET_SUBJECTS = {
    "asset:uk-carbon-intensity-48h": "urn:provider:electricside",
    "asset:owid-gbr-electricity-annual": "urn:provider:owid-open",
    "asset:gb-grid-aggregated-load": "urn:provider:electricside",
    "asset:derived:compute-power-correlation": "urn:provider:aggregated",
}
RESEARCH_PURPOSE = "compute-power-coordination-research"


@dataclass
class AccessRequest:
    asset: str                      # 目标 asset id
    consumer: str                   # 主体角色 id
    purpose: str | None             # 声明用途
    action: str                     # odrl action: analyze/distribute/aggregate
    derived_assets: list[str] = field(default_factory=list)  # 聚合输入（策略3场景）


@dataclass
class Decision:
    request_id: str
    ts_utc: str
    asset: str
    consumer: str
    purpose: str | None
    action: str
    matched_policy: str | None
    evaluation_trace: list[dict]
    decision: str                   # ALLOW / DENY / ALLOW_WITH_DUTY
    denial_code: str | None
    duties: list[str]
    escalation: dict | None
    latency_ms: float


class PDP:
    def __init__(self, policy_dir: Path = POLICY_DIR):
        self.policies: list[dict] = []
        for p in sorted(Path(policy_dir).glob("*.jsonld")):
            self.policies.append(json.loads(p.read_text(encoding="utf-8")))

    # ---------- 约束求值原语 ----------
    def _eval_constraint(self, c: dict, req: AccessRequest) -> tuple[bool, str]:
        left = c.get("odrl:leftOperand", c.get("leftOperand"))
        op = c.get("odrl:operator", c.get("operator"))
        right = c.get("odrl:rightOperand", c.get("rightOperand"))
        if isinstance(right, dict):
            right = right.get("@value", right.get("@id"))
        if left == "odrl:purpose":
            if op == "odrl:eq":
                return req.purpose == right, f"purpose '{req.purpose}' == '{right}'"
            if op == "odrl:neq":
                return req.purpose != right, f"purpose '{req.purpose}' != '{right}'"
        if left == "tdg:resultingLevel":
            rank = {"一般": 1, "important": 2, "核心": 3}
            return rank.get(req._derived_level, 0) >= rank.get(right, 99), \
                f"resultingLevel {req._derived_level} >= {right}"
        if left == "tdg:aggregateEscalation":
            return op == "odrl:isPartOf" and right == "tdg:highest-of-inputs", \
                f"escalation policy {right} acknowledged"
        return False, f"unhandled operand {left} ({op})"

    def _escalation_level(self, req: AccessRequest) -> str:
        """就高从严（规则包语义）：
        1. 等级取所有输入资产（聚合操作数）的最高值——目标衍生资产是输出，不计入输入
        2. 输入来自 ≥2 个不同主体（跨主体聚合）→ 至少升为"重要"
        """
        if req.action != "odrl:aggregate" or not req.derived_assets:
            return ""
        levels = [ASSET_LEVELS.get(a, "一般") for a in req.derived_assets]
        if "核心" in levels:
            return "核心"
        subjects = {ASSET_SUBJECTS.get(a, "unknown") for a in req.derived_assets}
        if "重要" in levels or len(subjects) >= 2:
            return "重要"
        return "一般"

    # ---------- 主求值 ----------
    def evaluate(self, req: AccessRequest) -> Decision:
        t0 = time.perf_counter()
        req._derived_level = self._escalation_level(req)
        trace: list[dict] = []
        matched, duties, escalation, denial = None, [], None, None
        decision = "DENY"

        candidates = [p for p in self.policies if p.get("target") == req.asset]
        trace.append({"step": "policy_lookup", "target": req.asset,
                      "candidates": [p["uid"] for p in candidates]})

        if not candidates:
            trace.append({"step": "no_policy", "note": "target uncovered"})
            decision = "DENY"
            denial = "ERR_NO_POLICY"
        else:
            # 1) prohibition：action 必须匹配；约束满足 = 禁令生效 = 拒绝
            for p in candidates:
                for pr in p.get("prohibition", []):
                    if pr.get("action") != req.action:
                        continue
                    for c in pr.get("constraint", []):
                        ok, note = self._eval_constraint(c, req)
                        trace.append({"step": "prohibition", "policy": p["uid"],
                                      "constraint": note, "applies": ok})
                        if ok:
                            matched = matched or p
                            denial = f"DENY_PROHIBITION_{c.get('odrl:leftOperand','').split(':')[-1]}"
            # 2) permission：action 必须匹配；全部约束满足才放行
            if not denial:
                for p in candidates:
                    granted = False
                    for pm in p.get("permission", []):
                        if pm.get("action") != req.action:
                            trace.append({"step": "permission_skip", "policy": p["uid"],
                                          "reason": f"action {pm.get('action')} != {req.action}"})
                            continue
                        all_ok = True
                        for c in pm.get("constraint", []):
                            ok, note = self._eval_constraint(c, req)
                            trace.append({"step": "permission", "policy": p["uid"],
                                          "constraint": note, "satisfied": ok})
                            all_ok = all_ok and ok
                        if all_ok:
                            granted = True
                            matched = p
                            for d_ in pm.get("duty", []):
                                name = d_.get("duty") or d_.get("action")
                                # 条件义务：tdg:reclassify 仅在升级判定生效时附加
                                if name == "tdg:reclassify":
                                    if req._derived_level in ("重要", "核心"):
                                        duties.append(name)
                                    continue
                                duties.append(name)
                            if req._derived_level in ("重要", "核心") and req.action == "odrl:aggregate":
                                escalation = {"rule": "tdg:aggregateEscalation",
                                              "inputs_level": req._derived_level,
                                              "reclassify_duty": True}
                                if "tdg:reclassify" not in duties:
                                    duties.append("tdg:reclassify")
                            decision = "ALLOW_WITH_DUTY" if duties else "ALLOW"
                            break
                    if granted:
                        break
                if not granted:
                    decision = "DENY"
                    denial = denial or "DENY_NO_PERMISSION_SATISFIED"

        latency = (time.perf_counter() - t0) * 1000
        return Decision(
            request_id=f"req-{uuid.uuid4().hex[:10]}",
            ts_utc=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            asset=req.asset, consumer=req.consumer, purpose=req.purpose,
            action=req.action, matched_policy=matched["uid"] if matched else None,
            evaluation_trace=trace, decision=decision, denial_code=denial,
            duties=duties, escalation=escalation, latency_ms=round(latency, 3))


if __name__ == "__main__":
    import sys
    pdp = PDP()
    demo = [
        AccessRequest("asset:uk-carbon-intensity-48h", "urn:consumer:computeside",
                      RESEARCH_PURPOSE, "odrl:analyze"),
        AccessRequest("asset:uk-carbon-intensity-48h", "urn:consumer:computeside",
                      "commercial-resale", "odrl:analyze"),
        AccessRequest("asset:derived:compute-power-correlation", "urn:consumer:computeside",
                      RESEARCH_PURPOSE, "odrl:aggregate",
                      ["asset:uk-carbon-intensity-48h", "asset:owid-gbr-electricity-annual"]),
    ]
    for r in demo:
        d = pdp.evaluate(r)
        print(f"{d.asset:45s} purpose={str(d.purpose)[:30]:32s} -> {d.decision:15s} ({d.denial_code or ''})")
