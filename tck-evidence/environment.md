# DSP 实测环境记录（目标机执行后填写）

> 本文件是 TCK 证据包的"环境锚定"部分：审阅者据此复现你的实测。执行完 runbook 后如实填写并随证据一起提交。

## 1. 执行环境

| 项 | 值（执行后填写） |
|---|---|
| 目标机 OS | 例：Ubuntu 22.04 / Windows 11 + Docker Desktop 4.x |
| Docker 版本（`docker --version`） | |
| Docker Compose 版本（`docker compose version`） | |
| 执行日期 | |
| 执行人 | |

## 2. 连接器版本锚定

| 项 | 值 |
|---|---|
| 模板仓库与 commit | `Engineering-Research-and-Development/tsg-examples` @ commit ______ |
| TRUE Connector 版本 | （见镜像 tag 或 compose 输出） |
| DSP 版本/profile | 例：DSP profile 0.8 / 2024-1 |
| 镜像 digest | 见 `image_digests.txt` |

## 3. 端口与路径变更记录

- 实际使用的端口：provider ______ / consumer ______（默认 8282 / 9292）
- `.env` 是否修改：是/否，改了哪些项：______

## 4. 执行结果对照（四步）

| 步骤 | 期望 | 实际（Agreed/Declined/状态码） | 备注 |
|---|---|---|---|
| ① catalog request | 返回 2 个 Asset | | |
| ②a negotiation allow | Agreed | | |
| ②b negotiation deny | Declined | | |
| ③ transfer + EDR | EDR 下发、传输成功 | | agreementId 已回填：是/否 |
| ④ derived aggregation | duty 校验/未定义区 | | |

## 5. 遇到的坑与绕过方式

1. （例：②b 的 @context 校验失败 → 在 policy JSON-LD 补全 context 后通过）
2.
3.

## 6. 证据清单核对

- [ ] `tck-evidence/` 全部交互日志（含时间戳、HTTP 状态码、完整 body）
- [ ] `provider_full.log` / `consumer_full.log`
- [ ] `image_digests.txt`
- [ ] agreementId 回填后重跑的 ③ 日志
