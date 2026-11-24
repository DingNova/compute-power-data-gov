# 算电协同场景下跨主体数据治理的开源实现与符合性验证
## ——公开可复现包（PRP）白皮书 v1.0

**作者**：【作者姓名（占位符）】
**署名单位**：【署名单位（占位符）】
**联系方式**：【邮箱（占位符）】
**版本**：v1.0 ｜ **日期**：2026-11-24 ｜ **仓库**：https://github.com/DingNova/compute-power-data-gov
**DOI**：【Zenodo DOI（占位符，发布后回填）】

---

## 摘要

"算电协同"（算力调度与电力调度的协同优化）要求电力侧与计算侧两个独立数据主体之间进行高频、可信的数据交换，但跨主体数据交换面临三重治理缺口：**授权链无协议级载体、分类分级无机器可执行规则、治理效果无订单化度量**。本工作交付一个完全开源、完全可复现的治理参考实现（Public Reproducible Package, PRP）：以 W3C ODRL 2.2 表达跨主体授权策略（含自定义"聚合就高从严升级"语义扩展），以策略驱动求值引擎（PDP）替代硬编码访问控制，以 DSP（Dataspace Protocol）2024-1 消息层校验保证交换报文的词汇表规范性，并以"订单化评测器"对治理工件做符合性度量。全部结论基于真实公开数据（英国国家电网 ESO Carbon Intensity API、OWID）与真实运行的批测实验：**48 组全因子访问决策矩阵 oracle 一致率 100%（越权拦截率 100%、误拒率 0%）、60 订单符合性评测缺陷检出率 100%（误报率 0%）、9/9 协议消息合法性判定正确**。本包同时沉淀两份标准意见草稿（TC601/TC609 方向、IEEE P4172）与三项上游开源贡献种子。

**关键词**：数据治理；算电协同；ODRL；Dataspace Protocol；分类分级；订单化评测；GB/T 43697-2024

---

## 1 背景与动机

### 1.1 算电协同的数据交换特征

算电协同的典型数据流：电力侧主体（电网/售电公司）持有负荷、碳强度、绿电占比等时序数据；计算侧主体（数据中心/算力运营商）持有算力负载与调度数据。协同优化需要双方就对方的时序数据达成**有条件的、可审计的**访问授权——条件包括使用目的（仅限协同研究）、义务（署名与许可保留）、以及**聚合衍生数据的风险升级**（两个"一般"级数据聚合可能形成"重要"级敏感信息）。

### 1.2 三重治理缺口

| 缺口 | 现状 | 本工作的回应 |
|---|---|---|
| 授权链无协议级载体 | 企业实践停留在合同 PDF + 邮件审批 | ODRL 机器可读策略 + 决策日志全留痕 |
| 分类分级无机器可执行规则 | GB/T 43697-2024 已发布但无开源实现，落地靠人工 Excel | 分级规则机器可读化 + "就高从严"聚合升级求值器 |
| 治理效果无度量 | "有治理"与"治理得好"无法区分 | 订单化评测器：缺陷检出率/误报率/耗时全部可统计 |

---

## 2 治理框架设计

### 2.1 总体架构

```
L1 数据接入层   真实公开源 + HTTP 全量日志留痕（授权链第一层证据）
      ↓
L2 策略层      5 条 ODRL 2.2 策略（JSON-LD，@context 本地锚定）
      ↓
L3 决策层      PDP 求值引擎：constraint 逐条求值 + 决策轨迹留痕
      ↓
L4 协议层      DSP 2024-1 消息构造 + JSON-LD expansion 真实校验
      ↓
L5 评测层      订单化评测器：目录符合性/分级符合性/授权链/质量三维度
```

### 2.2 ODRL 策略库（含语义扩展）

| 策略 | 语义 | 场景 |
|---|---|---|
| 策略 1a/1b | `odrl:analyze` / `odrl:distribute` 放行，约束 `purpose eq research`，义务 `attribute` | 研究用途合法访问 |
| 策略 2a/2b | `odrl:prohibit distribute`，约束 `purpose neq research` | 商业转售/未知第三方越权 |
| 策略 3 | 自定义 `tdg:aggregateEscalation`：聚合衍生数据的等级 = max(输入等级)，且输入跨 ≥2 主体时至少升为"重要"，附加 `tdg:reclassify` 条件义务 | 跨主体聚合衍生（GB/T 43697 衍生数据"就高从严"的机器可执行化） |

**策略 3 的语义扩展是本工作的方法学创新点**：ODRL 2.2 原生词汇没有"聚合升级"语义；本实现以自定义术语 + 求值器支持的方式落地国标规则，并将该缺口作为上游标准化议题（见 §6）。

### 2.3 分类分级映射

资产分级表（`policies/catalog/classification-mapping.md` 机器可读版）：Carbon Intensity 半小时数据、OWID 公开统计 = 一般级；多主体负荷聚合、算电相关性衍生数据 = 重要级。分级判定嵌入 PDP 求值器的升级规则，而非文档性描述。

---

## 3 参考实现

三个自研组件，全部纯 Python、零外部服务依赖、一次命令全量重跑（幂等）：

1. **PDP 求值引擎**（`pdp/engine.py`）：真实加载 5 条策略 JSON-LD；prohibition 优先（拒绝优先原则）；constraint 求值（purpose eq/neq）；跨主体聚合升级判定；条件义务（`tdg:reclassify` 仅在升级生效时附加）；输出含逐步求值轨迹的决策日志（JSONL）。
2. **DSP 协议消息层**（`pdp/dsp_msg.py`）：CatalogRequestMessage / ContractRequestMessage / TransferRequestMessage 构造器；pyld 真实执行 JSON-LD expansion；校验规则 = @type 展开为 DSP 命名空间 IRI + 全树属性 IRI 命名空间白名单（词汇表治理）；ODRL 与 DSP 2024-1 context 本地锚定（离线可复现）。
3. **订单化评测器**（`eval-engine/`）：任意数据集 schema 接入 → 自动输出符合性报告（JSON + Markdown），对齐"数据集质量测评向工具化、订单化转变"的政策方向；评测维度 = 目录符合性（8 必填字段）/ 分级词汇合规 / 许可声明 / 接入留痕 / 质量三维度（GB/T 36344 口径）。

---

## 4 实测结果（全部数据真实运行产出）

### 4.1 数据接入（L1）

- **UK Carbon Intensity API**（National Grid ESO 官方，免密钥）：144 条真实半小时记录（48h 实测+预测），请求/响应全量 HTTP 日志留痕；
- **OWID Energy Data**（GitHub commit `f8de88a4` 锚定）：GBR 26 条年度发电结构记录；
- 真实数据质量三维度实测：完整性 100%、时序一致性 PASS。

### 4.2 A/B 对照实验

同批真实数据、8 组跨主体访问尝试：**越权拦截率 0% → 100%、可审计率 0% → 100%**（v0 无治理基线 vs v1 治理后）。

### 4.3 全因子决策矩阵（48 组：4 asset × 4 主体角色 × 3 协议段）

| 轮次 | Oracle 一致率 | 批测自动检出的真实缺陷 |
|---|---|---|
| R1 | 50.0% | ① OWID 无策略覆盖（24 组 ERR_NO_POLICY）② 升级求值器未实现跨主体判定 ③ 目录可见性误走策略求值 |
| R2 | 70.8% | ④ prohibition 约束满足语义写反 ⑤ permission/prohibition 未校验 action 匹配 ⑥ 聚合输入集误含目标衍生资产 |
| R3 | **100%** | 拦截率 100%、误拒率 0%、P50 0.009ms |

**6 个缺陷全部由批测 oracle 自动检出，非人工发现**——治理规则包自身的质量也是被评测出来的。

### 4.4 订单化评测批测（60 订单：20 干净 + 40 注入缺陷 × 8 类）

| 轮次 | 缺陷检出率 | 误报率 | 检出情况 |
|---|---|---|---|
| R1 | 100% | 55% | 55% "误报"实为**源资产真实缺陷**（OWID asset `endpoint_template` 缺失，完整率 87.5%）被正确检出 |
| R2 | **100%** | **0%** | 准确率 100%，单订单评测 P50 0.016ms / P95 0.022ms |

个案闭环（2026-11-22）：订单 `ord-20261122T081937Z` 评测 REVIEW → 逮住分级词汇不规范 + 许可字段错位两处真实缺陷 → 修复 → 订单 `ord-20261122T082043Z` 复评 PASS。订单号可公开对账。

### 4.5 协议消息校验（L4 消息层）

5 条合法 DSP 2024-1 消息 + 4 条注入非法消息（缺 @context / 错误 @type / 缺协议必填字段 / 词汇表外术语）：**9/9 判定全部正确**。词汇表外术语经递归展开后被命名空间白名单捕获——验证了"词汇表治理"校验的必要性。

### 4.6 证据分层声明（诚实边界）

| 层级 | 证据 | 状态 |
|---|---|---|
| L1 数据接入 | HTTP 全量日志 | ✅ 实测 |
| L2 决策矩阵 | 48 组 JSONL 决策日志 | ✅ 实测 |
| L3 协议消息校验 | 9 消息校验日志 | ✅ 实测 |
| L4 连接器级报文 | dsp-true-connector 三段交互 | 🔄 参考实现就绪（runbook v2），实测为下一步工作 |

---

## 5 符合性自评矩阵

| 标准/规范 | 对齐点 | 本包实现 | 自评 |
|---|---|---|---|
| ODRL 2.2 (W3C REC) | Offer/Agreement/prohibition/permission/constraint/duty | 5 条策略 JSON-LD + 求值器 | ✅ |
| DSP 2024-1 (IDSA) | Catalog/Negotiation/Transfer 消息结构 | 消息构造器 + expansion 校验 | ✅（消息层） |
| GB/T 43697-2024 | 数据分类分级规则、衍生数据就高从严 | 分级表 + aggregateEscalation 求值器 | ✅（规则层） |
| GB/T 36344 | 质量维度（完整性/一致性/时效性） | 评测器三维度实测 | ✅ |
| GB/T 37964（方向） | 脱敏不可还原/聚合风险 | 聚合升级语义（演示级） | ⚠️ 部分 |
| ISO 8000 / DCAT | 元数据规范 | 8 必填字段目录符合性 | ✅ |

---

## 6 标准意见与上游开源贡献

1. **TC601/TC609 意见表草稿**（2 条，含实测支撑）：① 建议将"衍生数据分级"的可执行规则（含跨主体聚合升级）纳入标准正文并给出机器可读表达建议；② 建议配套符合性评测工具规范（订单化接口）。草稿见 `docs/tc609-draft.md`。
2. **IEEE P4172 技术意见草稿**：Entity 身份回路与策略决策点的衔接（本包 PDP 决策日志的 request_id/ts_utc 字段设计可直接对接）。见 `docs/ieee-p4172-draft.md`。
3. **上游 issue 种子 ×2**：① dsp-tck 未覆盖聚合衍生场景（附本包 48 组矩阵中聚合通道的实测用例）；② ODRL 社区：`aggregateEscalation` 词汇标准化提案素材（附策略 3 实现与求值轨迹）。

---

## 7 可复现性指南

```bash
git clone https://github.com/DingNova/compute-power-data-gov.git
cd compute-power-data-gov

# L1 数据接入（约 2 分钟，免密钥）
python scripts/ingest_carbon_intensity.py && python scripts/ingest_owid.py

# L3 决策矩阵（48 组，固定种子，幂等）
python pdp/run_matrix.py

# L4 消息校验（9 消息）
python pdp/dsp_msg.py

# L5 评测批测（60 订单，固定种子 20261124）
python eval-engine/batch_eval.py
```

依赖：Python ≥3.11、`pyld`（pip install pyld）。全部 context 本地锚定于 `pdp/contexts/`，离线可复现。版本锚定：见 `git log` 与 `tck-evidence/` 中各工件的时间戳。

---

## 8 下一步工作

1. **L4 升级**：在目标机按 `connector/runbook.md`（v2，路径 A：dsp-true-connector + MongoDB Docker）完成连接器级三段交互实测，将 L2 决策矩阵升级为协议级报文证据；
2. **脱敏验证扩展**：增加上下文重识别攻击 + membership inference 轨道，对齐 GB/T 37964 验证方法；
3. **上游贡献提交**：§6 的 2 个 issue 与 1 个标准化提案素材；
4. **标准化流程**：TC609/IEEE 意见表实名提交（【提交人（占位符）】）。

---

## 附录 A：工件清单

| 工件 | 路径 | 说明 |
|---|---|---|
| 决策矩阵报告 | `reports/matrix_report.md` | 含三轮迭代收敛记录 |
| 评测批测报告 | `reports/eval_batch_report.json/.md` | 含缺陷检出统计 |
| A/B 实验代码 | `ab-experiment/metrics.py` | 拦截率对照 |
| 决策日志 | `tck-evidence/pdp_evidence/decision_log.jsonl` | 48 组全轨迹 |
| 消息校验日志 | `tck-evidence/pdp_evidence/message_validation_log.json` | 9 消息明细 |
| 评测批测日志 | `tck-evidence/pdp_evidence/eval_batch_log.jsonl` | 60 订单明细 |
| ODRL 策略库 | `policies/odrl/*.jsonld` | 5 条策略 |
| 连接器 Runbook | `connector/runbook.md` | 路径 A 部署指南 |

## 附录 B：许可与数据来源声明

本包代码：【许可（占位符，建议 Apache-2.0 / MIT）】。数据来源：UK Carbon Intensity API（© National Grid ESO，公开 API）；OWID Energy Data（CC-BY-4.0，commit `f8de88a4` 锚定）。引用本白皮书时请同时引用上述数据来源之原始许可条款。

---

*本白皮书全部实测数据可由 §7 命令一键复现；如复现结果与本报告不符，请提 GitHub issue。*
