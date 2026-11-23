# Runbook v2：算电协同 DSP 治理流水线执行指南（2026-11-24 修订）

> **修订说明**：v1 引用的 `tsg-examples` 仓库已证实不存在（调研错误）。本版修正为：
> **主证据路径 = 自研 PDP + 协议消息层（已在本仓库跑通，无需目标机）**；
> **路径 A = dsp-true-connector 实测（stretch，需目标机）**；路径 B = TRUE Connector IDS v1（兜底）。

## 证据分层（重要）

| 层级 | 内容 | 载体 | 状态 |
|---|---|---|---|
| L1 真实数据 | Carbon Intensity/OWID 接入 + HTTP 全量日志 | `data/raw` + `data/logs` | ✅ 已完成 |
| L2 策略决策 | 48 组全因子决策矩阵（拦截率 100%） | `pdp/` + `reports/matrix_report.md` | ✅ 已完成（本机） |
| L3 协议消息 | DSP 2024-1 消息构造 + JSON-LD 机器校验 9/9 | `pdp/dsp_msg.py` | ✅ 已完成（本机） |
| L4 连接器实测 | dsp-true-connector 三段交互报文 | 目标机执行本 runbook 路径 A | ⬜ stretch |

L2/L3 已经构成"策略引擎+协议校验"的可复现证据闭环；L4 是锦上添花，**失败不影响任何确权成果**。

---

## 路径 A：dsp-true-connector 实测（目标机，预计 2–3 小时）

### 前置（约 20 分钟）

```bash
# 1. JDK 21 + Maven 3.9.4
java -version   # 需要 21.x
mvn -version    # 需要 3.9.4+

# 2. Docker 运行 MongoDB 7.0.12（provider/consumer 各一个库）
docker run -d --name mongo-dsp -p 27017:27017 mongo:7.0.12
```

### 构建与配置（约 30–40 分钟，含依赖下载）

```bash
git clone https://github.com/Engineering-Research-and-Development/dsp-true-connector.git
cd dsp-true-connector

# 跳过测试快速构建（集成测试用 Testcontainers，耗时长且需拉测试镜像）
mvn clean package -DskipTests -Dmaven.test.skip=true

# 关键配置文件（双实例各一份，按需改端口/Mongo URI）：
#   connector/src/main/resources/application-provider.properties
#   connector/src/main/resources/application-consumer.properties
#   connector/src/main/resources/initial_data-{provider,consumer}.json
```

### 启动双实例

```bash
# provider（默认 8090）
mvn -pl connector spring-boot:run -Dspring-boot.run.profiles=provider &
# consumer（另一个 shell）
mvn -pl connector spring-boot:run -Dspring-boot.run.profiles=consumer &
```

启动后打开 Swagger UI 找实际端点（openapi.md 有说明，通常 `http://localhost:8090/swagger-ui.html`）。把 Swagger 里的 catalog / contract negotiation / transfer 端点抄下来，填进本仓库 `run_dsp_flow.sh` 顶部的 `P=`/`C=` 环境变量（脚本已参数化）。

### 数据与策略注入

1. Asset 注册：`data/raw/*_asset_*.json` 中的元数据按 Swagger 的 catalog 管理 API 录入（或改 `initial_data-provider.json` 预置）
2. 策略挂载：`policies/odrl/policy{1,1b,2,2b,3}*.jsonld` 五条策略按 negotiation API 的 policy 录入格式转换后挂到对应 asset
3. 角色标注：provider=`urn:provider:electricside`，consumer=`urn:consumer:computeside`

### 四步交互抓痕

```bash
bash run_dsp_flow.sh <provider地址:端口> <consumer地址:端口>
```

| 步骤 | 期望 | 落盘 |
|---|---|---|
| ① catalog | 返回已注册 assets | `tck-evidence/01_catalog_request_*.log` |
| ②a 放行谈判（策略1） | Agreed | `tck-evidence/02_negotiation_allow_*.log` |
| ②b 越权拒绝（策略2） | Declined | `tck-evidence/02_negotiation_deny_*.log` |
| ③ transfer | EDR 下发 | `tck-evidence/03_transfer_process_*.log` |
| ④ 聚合衍生（策略3） | duty 校验/未定义区 | `tck-evidence/04_derived_aggregation_*.log` |

### 证据回传

```bash
docker logs mongo-dsp > mongo_full.log   # 不需要；连接器日志才要
# 连接器日志按启动方式取 stdout 或 logs/ 目录
docker images --digests > image_digests.txt
```

回传 `tck-evidence/`、连接器日志、`image_digests.txt`，填 `tck-evidence/environment.md`。

---

## 路径 B（兜底）：TRUE Connector IDS v1

仅当路径 A 卡死且仍有时间：`true-connector` 仓库自带 `docker-compose.yml`，纯 Docker 30 分钟起双端，但协议为 IDS v1（非 DSP），证据标注需降级。**当前不建议执行**。

## 已知坑

- **Java 版本**：README 早期写 Java 17，现已升级 **Java 21**（Maven 3.9.4 兼容）；装 21
- **Testcontainers**：`mvn clean verify` 需要 Docker 拉测试镜像，跳过测试构建即可
- **端口冲突**：provider 8090 起不来先查占用
- **Mongo 双库**：两个 profile 配置了不同 Mongo 连接，别共用一个库名
- **@context**：消息必须带 DSP context（本仓库 `pdp/contexts/` 已本地锚定 2024-1 版）
