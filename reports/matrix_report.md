# 48 组全因子决策矩阵批测报告

生成时间：2026-11-23T21:51:51.230679+00:00

| 指标 | 值 |
|---|---|
| 决策总数 | 48 |
| Oracle 一致率 | 100.0% |
| 越权拦截率 | 100.0% (20/20) |
| 误拒率 | 0.0% (0/28) |
| 延迟 P50/P95/max | 0.01 / 0.04 / 1.81 ms |

## 分段统计

| 协议段 | 总数 | DENY | ALLOW(+DUTY) |
|---|---|---|---|
| catalog | 16 | 0 | 16 |
| negotiation | 16 | 10 | 6 |
| transfer | 16 | 10 | 6 |

## 拒绝原因码分布

| 拒绝码 | 次数 |
|---|---|
| DENY_NO_PERMISSION_SATISFIED | 10 |
| DENY_PROHIBITION_purpose | 4 |
| ERR_NO_POLICY | 6 |

## 发现

- **[info]** asset gb-grid-aggregated-load lacks ODRL policy → negotiation/transfer ERR_NO_POLICY；目录可见但谈判拒绝，暴露策略缺口（评测器的价值证明）
## 迭代收敛记录（评测器价值实证）

| 轮次 | Oracle 一致率 | 检出缺陷 | 修复 |
|---|---|---|---|
| R1 | 50.0% | ①owid 无策略覆盖（24 组 ERR_NO_POLICY）②"就高从严"求值器未实现跨主体判定（一般+一般聚合未升级为重要）③目录可见性误走策略求值 | 补策略 1b/2b；求值器加跨主体升级规则；catalog 改 DCAT 注册表判定 |
| R2 | 70.8% | ④prohibition 约束满足语义写反（研究用途被误拒）⑤permission/prohibition 未校验 action 匹配 ⑥聚合输入集误含目标衍生资产 | 三处求值器修正 |
| R3 | 100% | — | 全因子一致，拦截率 100%，误拒率 0% |

R1/R2 的缺陷均由批测 oracle 自动检出，非人工发现——订单化评测方法学的自证。
