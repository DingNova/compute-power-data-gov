# Runbook：DSP 三段真实交互（目标机执行，约 1–2 小时）

> 在**任何一台装有 Docker 的机器**上执行。产出全部拉回本仓库 `data/logs/` 与 `tck-evidence/`。
> 主方案：TRUE Connector DSP 模板（IDSA DSP 一致性实测的事实标准载体）；备选：Eclipse EDC。

## 前置

```bash
docker --version        # 需要 20.10+
git clone https://github.com/Engineering-Research-and-Development/tsg-examples.git
cd tsg-examples/dsp     # DSP use case 模板（provider=电侧 / consumer=算侧）
```

## 配置覆盖（本仓库已备好，拷贝即用）

1. **Asset 注册**：把 `data/raw/*_asset_*.json` 中的 asset 元数据写入模板的 provider asset 配置
   （TRUE Connector 资源目录 `provider/resources`，具体文件名以模板 README 为准）。
2. **策略**：把 `policies/odrl/*.jsonld` 三个策略写入 provider 的 policy/contract definition 配置。
3. **角色标注**：provider 侧标注 `urn:provider:electricside`（电侧），consumer 侧 `urn:consumer:computeside`（算侧）。

## 跑三段交互

```bash
docker compose up -d
sleep 60                      # 等待全部容器就绪
bash ../../run_dsp_flow.sh    # 本仓库脚本，抓全量请求/响应（时间戳留痕）
```

`run_dsp_flow.sh` 依次执行并分别留痕：

| 步骤 | 期望结果 | 落盘文件 |
|---|---|---|
| ① catalog request | provider 返回 2 个 Asset 目录 | `tck-evidence/01_catalog_request.log` |
| ② contract negotiation（策略 1 放行 + 策略 2 越权拒绝） | 一个 Agreed、一个 Declined | `tck-evidence/02_negotiation_{allow,deny}.log` |
| ③ transfer process + EDR 获取（策略 1） | EDR token 下发，真实数据传输成功 | `tck-evidence/03_transfer_process.log` |
| ④ 聚合衍生请求（策略 3） | 触发 duty 校验/未定义区（这是实测差异点，如实记录） | `tck-evidence/04_derived_aggregation.log` |

```bash
docker compose logs provider > provider_full.log    # 全量容器日志也拉回
docker compose logs consumer > consumer_full.log
```

## 拉回证据

把 `tck-evidence/`、`*.log` 与交互时间戳提交回本仓库（push 或发我打包）。日志必须含：
- DSP 版本 / TRUE Connector 版本 / Docker 镜像 digest（`docker images --digests`）
- 每次交互的时间戳、HTTP 状态码、完整 JSON body

## 已知坑（提前提醒）

- **VC/JSON-LD context**：TRUE Connector 对 `@context` 缺失会直接拒 negotiation；策略文件必须带完整 context。
- **EDR token**：transfer 后需从 consumer 的 EDR 缓存取 token 再调 data plane；模板自带脚本，别手拼。
- **端口占用**：模板默认 8282/9292/4243 等，目标机被占时改 `.env`。
- 若 DSP 模板跑不通：备选 Eclipse EDC minimum runtime（docs 里有 gradle/Docker 双路径），同样按本 runbook 的四步留痕。
