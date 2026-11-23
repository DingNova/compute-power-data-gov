# A/B 效果看板（开发态 PDP 首轮）

- 生成时间: 2026-11-22T08:18:57.712924+00:00
- 数据基础: 真实公开数据（UK Carbon Intensity API 48h 实测 + OWID GBR 年度, commit f8de88a4）
- 目录覆盖率: 100.0% (3/3 Asset 有分类分级元数据)

| 指标 | v0 无治理 | v1 治理后 |
|---|---|---|
| 越权拦截率 | 0.0% | **100.0%** |
| 越权决策可审计率 | 0.0% | **100.0%** |
| 单次判定时延 | ~0.0ms | ~0.0ms |

## 逐次判定明细（v1）

| # | Asset | Action | Purpose | 判定 | 策略 |
|---|---|---|---|---|---|
| t01 | asset:uk-carbon-intensity-48h | odrl:analyze | compute-power-coordination-research | ALLOWED | policy:carbon-intensity-analysis-allow |
| t02 | asset:uk-carbon-intensity-48h | odrl:distribute | commercial-resale | DENIED | policy:carbon-intensity-export-deny |
| t03 | asset:uk-carbon-intensity-48h | odrl:analyze | compute-power-coordination-research | ALLOWED | policy:carbon-intensity-analysis-allow |
| t04 | asset:owid-gbr-electricity-annual | odrl:aggregate | compute-power-coordination-research | ALLOWED_WITH_DUTY | policy:derived-aggregation-escalation |
| t05 | asset:derived:compute-power-correlation | odrl:distribute | commercial-resale | DENIED | policy:carbon-intensity-export-deny |
| t06 | asset:owid-gbr-electricity-annual | odrl:aggregate | commercial-resale | DENIED | policy:carbon-intensity-export-deny |
| t07 | asset:uk-carbon-intensity-48h | odrl:distribute | public-disclosure-attributed | DENIED | policy:carbon-intensity-export-deny |
| t08 | asset:owid-gbr-electricity-annual | odrl:analyze | compute-power-coordination-research | ALLOWED | policy:carbon-intensity-analysis-allow |

> 复现命令: `python ab-experiment/metrics.py`；v0/v1 为治理效果对照，非业务上线效果。