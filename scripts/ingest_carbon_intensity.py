#!/usr/bin/env python3
"""
真实数据接入：UK Carbon Intensity API（National Grid ESO 官方）
- 免密钥公开 API，真实时序（碳强度 + 发电结构/绿电占比）
- 每次请求保存完整 HTTP 请求/响应日志（授权链与可审计性证据）
- 输出注册为 EDC Asset 的元数据描述文件
"""
import json
import ssl
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LOGS = ROOT / "data" / "logs"
RAW.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)

BASE = "https://api.carbonintensity.org.uk"
CTX = ssl.create_default_context()
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
LOG_FILE = LOGS / f"http_{RUN_ID}_carbon_intensity.jsonl"

UA = "compute-power-gov-prp/0.1 (research; public data ingestion; contact via repo issues)"


def log_http(entry: dict):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def fetch(path: str, label: str) -> dict:
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    t0 = datetime.now(timezone.utc)
    try:
        with urllib.request.urlopen(req, timeout=30, context=CTX) as resp:
            body = resp.read()
            entry = {
                "ts_utc": t0.isoformat(),
                "method": "GET",
                "url": url,
                "status": resp.status,
                "resp_headers": dict(resp.headers),
                "resp_bytes": len(body),
                "duration_ms": int((datetime.now(timezone.utc) - t0).total_seconds() * 1000),
                "label": label,
            }
            log_http(entry)
            return {"label": label, "path": path, "ts_utc": t0.isoformat(), "body": json.loads(body)}
    except Exception as e:  # 失败也留痕
        log_http({"ts_utc": t0.isoformat(), "method": "GET", "url": url, "error": repr(e), "label": label})
        raise


def main():
    now = datetime.now(timezone.utc)
    from_48h = (now - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%MZ")
    to_next24 = (now + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%MZ")

    results = []
    # 1) 当前瞬时发电结构（含绿电占比）
    results.append(fetch("/generation", "generation_now"))
    # 2) 当前碳强度
    results.append(fetch("/intensity", "intensity_now"))
    # 3) 过去48小时实测碳强度（真实时序，半小时粒度）
    results.append(fetch(f"/intensity/{from_48h}/{to_next24}", "intensity_48h_actual_plus_forecast"))
    # 4) 过去48小时发电结构（风电/太阳能占比，真实时序）
    results.append(fetch(f"/generation/{from_48h}/{to_next24}", "generation_48h"))

    for r in results:
        out = RAW / f"{RUN_ID}_{r['label']}.json"
        out.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        n = len(r["body"].get("data", [])) if isinstance(r["body"].get("data"), list) else "-"
        print(f"[ok] {r['label']}: {r['path']} -> {out.name} ({n} records)")

    # 生成 EDC Asset 元数据描述（策略注册用）
    asset = {
        "asset_id": "uk-carbon-intensity-48h",
        "title": "UK National Grid ESO Carbon Intensity & Generation Mix (48h)",
        "classification": {
            "framework": "能源行业数据分类分级指南（2026年版）× GB/T 43697-2024",
            "level": "一般",
            "rationale": "公开发布的电网运行公开数据，不涉及个人、重要或核心数据；聚合口径为全国公开统计",
        },
        "endpoint_template": BASE + "/intensity/{from}/{to}",
        "pull_evidence": {
            "run_id": RUN_ID,
            "http_log": f"data/logs/http_{RUN_ID}_carbon_intensity.jsonl",
            "raw_files": [f"data/raw/{RUN_ID}_{r['label']}.json" for r in results],
        },
        "license": "开放使用（API 文档条款），拉取时间与请求响应全量留痕",
    }
    (RAW / f"{RUN_ID}_asset_uk-carbon-intensity-48h.json").write_text(
        json.dumps(asset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[asset] EDC Asset 描述 -> data/raw/{RUN_ID}_asset_uk-carbon-intensity-48h.json")
    print(f"[log]   HTTP 日志 -> {LOG_FILE}")


if __name__ == "__main__":
    sys.exit(main())
