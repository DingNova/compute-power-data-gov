"""
pdp/dsp_msg.py — DSP 2024-1 协议消息构造与 JSON-LD 真实校验层

构造 DSP catalog / contract negotiation / transfer 三段消息，
用 pyld 真实执行 JSON-LD expansion 校验 @context 与术语合法性，
输出消息校验日志（合法/非法样本均留痕）。

这就是"协议级证据"的自研最小可信层：消息符合 DSP 词汇表由 expansion
机器校验证明，不依赖任何外部连接器可运行性。
"""
from __future__ import annotations

import copy
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

from pyld import jsonld

REPO = Path(__file__).resolve().parent
CTX_DIR = REPO / "contexts"
EV = REPO.parent / "tck-evidence" / "pdp_evidence"
REPORTS = REPO.parent / "reports"
EV.mkdir(parents=True, exist_ok=True)

ODRL_CTX_URL = "https://www.w3.org/ns/odrl.jsonld"
DSP_CTX_URL = "https://w3id.org/dspace/2024/1/context.jsonld"

# 本地 context 锚定（可复现：不依赖运行时外网）
_LOCAL = {
    ODRL_CTX_URL: CTX_DIR / "odrl.jsonld",
    DSP_CTX_URL: CTX_DIR / "dsp_2024-1_context.jsonld",
}


def _local_loader(url: str, options: dict | None = None):
    import urllib.request
    if url in _LOCAL:
        return {"document": json.loads(_LOCAL[url].read_text(encoding="utf-8")),
                "documentUrl": url, "contextUrl": None}
    with urllib.request.urlopen(url, timeout=20) as r:
        return {"document": json.loads(r.read().decode("utf-8")),
                "documentUrl": url, "contextUrl": None}


jsonld.set_document_loader(_local_loader)

DSP_CTX = DSP_CTX_URL
BOTH_CTX = [DSP_CTX_URL, ODRL_CTX_URL]


class MessageFactory:
    """DSP 2024-1 消息构造器"""

    @staticmethod
    def catalog_request() -> dict:
        return {"@context": DSP_CTX, "@type": "dspace:CatalogRequestMessage",
                "dspace:datasetPartition": {}, "dspace:filter": []}

    @staticmethod
    def contract_request(offer_id: str, target: str, consumer_pid: str,
                         purpose: str | None = None) -> dict:
        msg = {"@context": BOTH_CTX, "@type": "dspace:ContractRequestMessage",
               "dspace:consumerPid": consumer_pid,
               "dspace:offer": {"@type": "odrl:Offer", "@id": offer_id,
                                "odrl:target": {"@id": target}},
               "dspace:callbackAddress": "http://localhost:9292/callback"}
        if purpose:
            msg["dspace:offer"]["odrl:purpose"] = purpose
        return msg

    @staticmethod
    def transfer_request(agreement_id: str, consumer_pid: str, data_url: str) -> dict:
        return {"@context": BOTH_CTX, "@type": "dspace:TransferRequestMessage",
                "dspace:consumerPid": consumer_pid,
                "dspace:agreementId": {"@id": agreement_id},
                "dspace:dataAddress": {"@type": "dspace:DataAddress",
                                       "dspace:baseUrl": data_url},
                "dspace:callbackAddress": "http://localhost:9292/callback"}

    @staticmethod
    def derived_aggregation_request(consumer_pid: str, operand_assets: list[str]) -> dict:
        """策略3 场景：自定义 tdg 词汇的聚合衍生请求（上游 issue 证据载体）"""
        return {"@context": BOTH_CTX + [{"tdg": "https://w3id.org/tdg/vocab#"}],
                "@type": "dspace:ContractRequestMessage",
                "dspace:consumerPid": consumer_pid,
                "dspace:offer": {"@type": "odrl:Offer",
                                 "@id": "policy:derived-aggregation-escalation",
                                 "odrl:target": {"@id": "asset:derived:compute-power-correlation"},
                                 "tdg:operandAssets": [{"@id": a} for a in operand_assets]},
                "dspace:callbackAddress": "http://localhost:9292/callback"}


def validate(msg: dict) -> dict:
    """pyld expansion 真实校验：@context 可解析 + @type 术语可展开 + 无未定义词汇"""
    t0 = time.perf_counter()
    errors = []
    try:
        expanded = jsonld.expand(copy.deepcopy(msg),
                                 options={"documentLoader": _local_loader})
    except Exception as e:  # context 解析失败、JSON 结构错误等
        errors.append(f"expansion_error: {type(e).__name__}: {e}")
        expanded = None
    if expanded is not None:
        # @type 必须展开成 IRI（expansion 后为字符串数组）
        types = [t for e in expanded if isinstance(e, dict)
                 for t in e.get("@type", []) if isinstance(t, str)]
        if not types or not any(t.startswith(("https://w3id.org/dspace", "http://www.w3.org/ns/odrl"))
                                for t in types):
            errors.append("no_type_iri: @type 未展开为 DSP/ODRL 命名空间 IRI（context 缺失或不匹配）")
        # 属性 IRI 必须落在已知命名空间白名单内（ Vocabulary Governance）
        KNOWN_NS = ("https://w3id.org/dspace/", "http://www.w3.org/ns/odrl/2/",
                    "https://w3id.org/tdg/vocab#", "http://purl.org/dc/terms/",
                    "http://www.w3.org/ns/dcat#", "http://www.w3.org/2001/XMLSchema#",
                    "https://w3id.org/security#", "https://www.w3.org/2018/credentials#",
                    "http://xmlns.com/foaf/0.1/", "http://creativecommons.org/ns#",
                    "http://www.w3.org/1999/02/22-rdf-syntax-ns#")
        for e in expanded:
            def _walk(node):
                if isinstance(node, dict):
                    for k, v in node.items():
                        if not k.startswith("@") and not k.startswith(KNOWN_NS):
                            errors.append(f"vocabulary_governance_violation: {k}")
                        _walk(v)
                elif isinstance(node, list):
                    for it in node:
                        _walk(it)
            _walk(e)
    latency = (time.perf_counter() - t0) * 1000
    return {"valid": not errors, "errors": errors,
            "expanded_types": types if expanded else [],
            "latency_ms": round(latency, 3)}


def main():
    f = MessageFactory()
    # 合法样本
    valid_msgs = [
        ("catalog_request", f.catalog_request()),
        ("contract_request_research", f.contract_request(
            "policy:carbon-intensity-analysis-allow",
            "asset:uk-carbon-intensity-48h", "urn:uuid:consumer-computeside",
            "compute-power-coordination-research")),
        ("contract_request_resale", f.contract_request(
            "policy:carbon-intensity-export-deny",
            "asset:uk-carbon-intensity-48h", "urn:uuid:consumer-computeside",
            "commercial-resale")),
        ("transfer_request", f.transfer_request(
            "urn:uuid:agreement-demo-001", "urn:uuid:consumer-computeside",
            "https://api.carbonintensity.org.uk/generation")),
        ("derived_aggregation", f.derived_aggregation_request(
            "urn:uuid:consumer-computeside",
            ["asset:uk-carbon-intensity-48h", "asset:owid-gbr-electricity-annual"])),
    ]
    # 非法样本（注入缺陷：评测器应真实逮住）
    m = f.catalog_request(); del m["@context"]
    invalid_msgs = [("invalid_missing_context", m)]
    m = f.contract_request("policy:x", "asset:y", "urn:uuid:c"); m["@type"] = "NotARealMessageType"
    invalid_msgs.append(("invalid_unknown_type", m))
    m = f.derived_aggregation_request("urn:uuid:c", ["asset:a"])
    invalid_msgs.append(("invalid_unbound_term",
                         {**m, "dspace:offer": {**m["dspace:offer"], "tdgX:typoTerm": 1}}))
    m = f.transfer_request("urn:uuid:a", "urn:uuid:c", "https://x")
    invalid_msgs.append(("invalid_bad_json_context", {**m, "@context": "https://invalid.example/none"}))

    log = []
    for name, msg in valid_msgs + invalid_msgs:
        r = validate(msg)
        entry = {"message": name, "expected_valid": name.startswith(("catalog", "contract", "transfer", "derived")),
                 **r, "msg_sha256": __import__("hashlib").sha256(
                     json.dumps(msg, sort_keys=True).encode()).hexdigest()[:16]}
        log.append(entry)

    n = len(log)
    tp = sum(1 for e in log if e["expected_valid"] == e["valid"])
    lat_v = sorted(e["latency_ms"] for e in log if e["valid"])
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protocol": "Dataspace Protocol (DSP) profile v0.8 context + ODRL 2.0",
        "validation_engine": "pyld jsonld.expand (real JSON-LD processing)",
        "local_contexts": {u: str(p.name) for u, p in _LOCAL.items()},
        "total_messages": n,
        "valid": sum(1 for e in log if e["valid"]),
        "invalid": sum(1 for e in log if not e["valid"]),
        "verdict_accuracy": round(tp / n, 4),
        "expansion_latency_ms": {"p50": round(statistics.median(lat_v), 3),
                                 "max": round(max(lat_v), 3)} if lat_v else None,
        "invalid_cases_detected": [e["message"] for e in log if not e["valid"]],
        "detail": log,
    }
    (EV / "message_validation_log.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in
                      ["total_messages", "valid", "invalid", "verdict_accuracy",
                       "invalid_cases_detected", "expansion_latency_ms"]},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
