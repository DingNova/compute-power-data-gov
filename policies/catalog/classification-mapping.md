# 分类分级 → ODRL 策略映射（L1 规则包核心）

> 依据：《能源行业数据分类分级指南（2026 年版）》× GB/T 43697-2024（一般/重要/核心三级）。
> 每条策略在 DSP 流程中真实生效：目录可见性（catalog filter）→ 合约谈判（contract negotiation）→ 传输（transfer）三段均有对应行为。

## 数据项定级（真实公开数据）

| Asset | 内容 | 级别 | 依据 |
|---|---|---|---|
| `uk-carbon-intensity-48h` | 电网公开碳强度/发电结构时序 | **一般** | 官方公开发布，无个人/聚合敏感性 |
| `owid-gbr-electricity-annual` | 公开年度电力统计 | **一般**（独立） | 公开统计；作跨主体聚合输入时触发衍生评估 |
| （演示）`derived:compute-power-correlation` | 跨主体聚合衍生数据 | **重要（就高从严）** | 聚合两个及以上主体数据 → 等级取最高，演示升级判定 |

## 策略 1：一般数据放行（usage: Analysis with Attribution）

```jsonld
{
  "@context": "https://www.w3.org/ns/odrl.jsonld",
  "@type": "Offer",
  "uid": "policy:carbon-intensity-analysis-allow",
  "assigner": {"uid": "urn:provider:electricside"},
  "target": "asset:uk-carbon-intensity-48h",
  "permission": [{
    "action": "odrl:analyze",
    "constraint": [{
      "odrl:leftOperand": "odrl:purpose",
      "odrl:operator": "odrl:eq",
      "odrl:rightOperand": {"@value": "compute-power-coordination-research"}
    }],
    "duty": [{
      "action": "odrl:attribute",
      "duty": "attribute-source-and-license"
    }]
  }]
}
```

## 策略 2：越权拒绝（超范围导出 / 未授权用途）

```jsonld
{
  "@context": "https://www.w3.org/ns/odrl.jsonld",
  "@type": "Offer",
  "uid": "policy:carbon-intensity-export-deny",
  "assigner": {"uid": "urn:provider:electricside"},
  "target": "asset:uk-carbon-intensity-48h",
  "prohibition": [{
    "action": "odrl:distribute",
    "constraint": [{
      "odrl:leftOperand": "odrl:purpose",
      "odrl:operator": "odrl:neq",
      "odrl:rightOperand": {"@value": "compute-power-coordination-research"}
    }]
  }]
}
```

DSP 行为：consumer 以 `purpose=commercial-resale` 发起 contract negotiation → provider 拒绝 → negotiation 进入 declined，日志留痕。

## 策略 3：衍生数据跨主体聚合"就高从严"升级（实测差异种子）

ODRL 核心词表**没有**表达"聚合后等级取输入最高值"的原生 leftOperand。本规则包定义自定义扩展并提交上游：

```jsonld
{
  "@context": ["https://www.w3.org/ns/odrl.jsonld", {
    "tdg": "https://w3id.org/tdg/vocab#"   /* 本规则包词汇表：Trusted Data Governance */
  }],
  "@type": "Agreement",
  "uid": "policy:derived-aggregation-escalation",
  "target": "asset:derived:compute-power-correlation",
  "permission": [{
    "action": "odrl:aggregate",
    "constraint": [{
      "odrl:leftOperand": "tdg:aggregateEscalation",
      "odrl:operator": "odrl:isPartOf",
      "odrl:rightOperand": {"@id": "tdg:highest-of-inputs"}
    }],
    "duty": [{
      "action": "tdg:reclassify",
      "constraint": [{
        "odrl:leftOperand": "tdg:resultingLevel",
        "odrl:operator": "odrl:gteq",
        "odrl:rightOperand": {"@value": "important"}   /* 一般+一般聚合 → ≥重要 */
      }]
    }]
  }]
}
```

**上游意见（将提为 issue）**：dsp-tck 用例集未覆盖"跨 Asset 聚合衍生的等级升级"场景；ODRL 缺少标准化的 `aggregateEscalation` 语义；DSP 2025-1 的 contract negotiation 对 Offer 中 duty/constraint 组合的校验行为在 aggregator 场景存在未定义区。依据 = 下方 A/B 实测中策略 3 的真实判定样例。

## 三段交互 × 策略对照

| DSP 段 | 策略 1 放行 | 策略 2 拒绝 | 策略 3 升级 |
|---|---|---|---|
| catalog | Asset 可见 | Asset 可见 | 可见但标注衍生 |
| contract negotiation | Offer → Agreed | Offer → **Declined**（日志含拒绝原因） | Agreed + duty 校验 |
| transfer | EDR 下发，传输成功 | 无 EDR（未进入） | EDR 下发带 reclassify 义务 |
