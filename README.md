# Compute–Power Coordination Data Governance PRP（算电协同跨主体数据治理 · 公开可复现包）

> **公开可复现包（Public Reproducibility Package, PRP）**：算电协同跨主体数据治理的开源实现与符合性验证。
> 真实公开算电数据接入 → ODRL 使用控制 → DSP 三段真实交互实测 → TC609 / IEEE P4172 标准意见。

---

## ⚠️ 定位与免责（必读）

- 本项目是**开源环境中的端到端技术验证**，不是官方测评/认证，未在央企或任何生产环境部署。
- 由**个人/课题组独立完成**，与任何官方机构、标准组织秘书处无关。
- DSP 三段交互通过仅证明特定构建在特定版本组合下的**协议行为一致性**，不自动证明安全、性能、治理或法律合规。
- 所有外部提交均如实标注状态：**已提交 ≠ 已采纳 ≠ 已收录**。

---

## 数据来源与许可（真实公开数据，逐条标注）

| 数据源 | 内容 | 许可 | 接入方式 | 本项目用途 |
|---|---|---|---|---|
| **UK Carbon Intensity API**（National Grid ESO 官方） | 半小时级碳强度 + 发电结构（风电/太阳能等绿电占比），含 forecast 与 actual | 开放使用（参见 API 文档） | 免密钥 HTTPS API，请求/响应全量留痕 | 电侧真实时序数据（负荷替代性指标 + 绿电占比），注册为 EDC Asset |
| **OWID Energy Data**（GitHub: owid/energy-data） | 各国发电量/电力结构年度序列 | CC-BY-4.0 | GitHub raw 直取（commit 锚定） | 跨主体聚合场景的第二个真实数据项（衍生数据"就高从严"判定样例） |
| Open Power System Data | 欧洲电力时序 | CC-BY-4.0（见表内各原始源） | 备选源 | 备选 |

算侧输入：公开权威指标表（明确标注为**外部参照值**，非本项目实测）。
本项目**不发布**任何真实敏感能源原始数据、设施坐标或调度指令；仅保留公开数据的拉取日志与派生统计。

---

## 目录结构

```
connector/        DSP 双端连接器部署（docker-compose + runbook，在目标机运行）
data/             真实数据拉取原始文件 + HTTP 请求/响应日志 + 许可记录
policies/         分类分级 → ODRL 策略库（放行 / 越权拒绝 / 衍生聚合升级）
ab-experiment/    v0 无治理基线 vs v1 治理后 A/B 对照实验与指标计算
eval-engine/      订单化评测器：任意数据集 schema 接入 → 治理符合性报告
tck-evidence/     DSP 交互证据包（版本/角色/覆盖模块/用例明细/原始日志）
docs/             执行计划、标准对照、TC609/IEEE 意见草稿
landing-page/     公开入口页（六块结构）
scripts/          数据接入与实验复现脚本
```

---

## 一键复现

```bash
# 1. 数据接入（免密钥，本机即可）
python scripts/ingest_carbon_intensity.py
python scripts/ingest_owid.py

# 2. DSP 三段交互（需 Docker，见 connector/runbook.md）
cd connector && docker compose up -d && bash run_dsp_flow.sh

# 3. A/B 指标与评测报告
python ab-experiment/metrics.py --logs data/logs/ --out ab-experiment/results/
python eval-engine/evaluate.py --schema policies/catalog --logs data/logs/ --out reports/
```

---

## 状态声明

| 事项 | 状态 |
|---|---|
| 数据接入 | ✅ 真实公开 API 拉取完成（见 data/logs） |
| DSP 三段交互 | 🔄 脚本就绪，目标机执行中 |
| ODRL 策略放行/拒绝 | 🔄 待 DSP 实测 |
| 上游 issue/PR | ⬜ 计划提交 |
| TC609 意见表 | 🔄 草稿就绪，窗口内提交 |
| IEEE P4172 技术意见 | 🔄 草稿就绪，工作组通道提交 |
