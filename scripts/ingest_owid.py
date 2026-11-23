#!/usr/bin/env python3
"""
真实数据接入 #2：OWID Energy Data（GitHub: owid/energy-data，CC-BY-4.0）
- GitHub 托管 → 用 GitHub API 锚定 commit SHA 作为数据版本（授权链叙事：数据版本可追溯）
- 只拉取 GBR（英国）电力结构子集，作为跨主体聚合场景的第二真实数据项
"""
import json
import ssl
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LOGS = ROOT / "data" / "logs"
RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
LOG_FILE = LOGS / f"http_{RUN_ID}_owid.jsonl"
CTX = ssl.create_default_context()
UA = "compute-power-gov-prp/0.1 (research; public data ingestion)"


def log_http(entry):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def fetch(url, label, max_bytes=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    t0 = datetime.now(timezone.utc)
    with urllib.request.urlopen(req, timeout=60, context=CTX) as resp:
        body = resp.read(max_bytes) if max_bytes else resp.read()
        log_http({
            "ts_utc": t0.isoformat(), "method": "GET", "url": url,
            "status": resp.status, "resp_bytes": len(body),
            "duration_ms": int((datetime.now(timezone.utc) - t0).total_seconds() * 1000),
            "label": label,
        })
        return resp.status, body


def main():
    # 1) GitHub API 拿默认分支最新 commit SHA（数据版本锚）
    status, body = fetch("https://api.github.com/repos/owid/energy-data/commits/master", "commit_anchor")
    sha = json.loads(body)["sha"]
    print(f"[anchor] owid/energy-data @ {sha[:12]}")

    # 2) 拉取数据 CSV（CC-BY-4.0，锚定该 commit）
    csv_url = f"https://raw.githubusercontent.com/owid/energy-data/{sha}/owid-energy-data.csv"
    status, body = fetch(csv_url, "owid_energy_csv")
    lines = body.decode("utf-8").splitlines()
    header = lines[0].split(",")
    # 提取 GBR 的电力相关列，构造跨主体聚合样例数据
    col_year = header.index("year")
    gbr_rows = [ln.split(",") for ln in lines if ",GBR," in ln]
    keep_cols = {
        "year": col_year,
        "wind_electricity": header.index("wind_electricity"),
        "solar_electricity": header.index("solar_electricity"),
        "hydro_electricity": header.index("hydro_electricity"),
        "low_carbon_electricity": header.index("low_carbon_electricity"),
        "fossil_electricity": header.index("fossil_electricity"),
        "electricity_generation": header.index("electricity_generation"),
    }
    subset = []
    for row in gbr_rows:
        try:
            rec = {k: (float(row[i]) if row[i] else None) for k, i in keep_cols.items()}
            if rec["year"] >= 2000:
                subset.append(rec)
        except (ValueError, IndexError):
            continue

    out = RAW / f"{RUN_ID}_owid_gbr_electricity_2000plus.json"
    out.write_text(json.dumps({
        "source": csv_url, "commit_sha": sha, "license": "CC-BY-4.0 (OWID)",
        "pulled_utc": RUN_ID, "records": subset,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] GBR 电力结构 {len(subset)} 条（2000-今） -> {out.name}")

    # EDC Asset 描述（第二真实数据项）
    asset = {
        "asset_id": "owid-gbr-electricity-annual",
        "title": "OWID Great Britain Electricity Generation by Source (annual, 2000+)",
        "license": "CC-BY-4.0 (OWID)",
        "classification": {
            "framework": "能源行业数据分类分级指南（2026年版）× GB/T 43697-2024",
            "level": "一般",
            "rationale": "公开发布的年度统计；作为跨主体聚合演示输入时，由策略 3 触发衍生数据就高从严评估（见 policies/odrl）",
        },
        "data_version_anchor": {"host": "github.com/owid/energy-data", "commit": sha, "license": "CC-BY-4.0"},
        "pull_evidence": {"run_id": RUN_ID, "http_log": f"data/logs/http_{RUN_ID}_owid.jsonl",
                          "raw_files": [out.name]},
    }
    (RAW / f"{RUN_ID}_asset_owid-gbr-electricity-annual.json").write_text(
        json.dumps(asset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[asset] EDC Asset 描述 -> data/raw/{RUN_ID}_asset_owid-gbr-electricity-annual.json")
    print(f"[log]   HTTP 日志 -> {LOG_FILE}")


if __name__ == "__main__":
    main()
