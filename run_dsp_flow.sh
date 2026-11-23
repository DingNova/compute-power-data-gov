#!/usr/bin/env bash
# DSP 三段交互抓痕脚本（目标机运行，与 connector/runbook.md 配套）
# 用法: bash run_dsp_flow.sh <provider_host:port> <consumer_host:port>
set -euo pipefail
EV=tck-evidence; mkdir -p "$EV"
P=${1:-localhost:8282}; C=${2:-localhost:9292}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
HDR(){ curl -sS -v -H "Content-Type: application/json" "$@" 2>&1 | tee "$EV/$1_$STAMP.log"; }

# ① catalog request（consumer → provider）
cat > /tmp/catalog.json <<'EOF'
{"@context":"https://w3id.org/dspace/v0.8/context.jsonld","@type":"CatalogRequestMessage","filter":[],"datasetPartition":{}}
EOF
HDR 01_catalog_request "http://$P/catalog/request" -d @/tmp/catalog.json

# ②a contract negotiation — 策略1（放行路径）
cat > /tmp/nego_allow.json <<'EOF'
{"@context":"https://w3id.org/dspace/v0.8/context.jsonld","@type":"ContractRequestMessage","consumerPid":"urn:uuid:consumer-computeside","offer":{"@type":"Offer","id":"policy:carbon-intensity-analysis-allow","target":"asset:uk-carbon-intensity-48h"},"callbackAddress":"http://localhost:9292/callback"}
EOF
HDR 02_negotiation_allow "http://$P/contract/negotiations" -d @/tmp/nego_allow.json

# ②b contract negotiation — 策略2（越权拒绝路径：purpose=commercial-resale）
cat > /tmp/nego_deny.json <<'EOF'
{"@context":"https://w3id.org/dspace/v0.8/context.jsonld","@type":"ContractRequestMessage","consumerPid":"urn:uuid:consumer-computeside","offer":{"@type":"Offer","id":"policy:carbon-intensity-export-deny","target":"asset:uk-carbon-intensity-48h","purpose":"commercial-resale"},"callbackAddress":"http://localhost:9292/callback"}
EOF
HDR 02_negotiation_deny "http://$P/contract/negotiations" -d @/tmp/nego_deny.json

# ③ transfer process（用 ②a 拿到的 agreementId，占位脚本提示替换）
cat > /tmp/transfer.json <<'EOF'
{"@context":"https://w3id.org/dspace/v0.8/context.jsonld","@type":"TransferRequestMessage","consumerPid":"urn:uuid:consumer-computeside","agreementId":"REPLACE_WITH_AGREEMENT_ID_FROM_STEP_2A","dataAddress":{"@type":"DataAddress","type":"HttpData","baseUrl":"https://api.carbonintensity.org.uk/generation"},"callbackAddress":"http://localhost:9292/callback"}
EOF
HDR 03_transfer_process "http://$P/transfers" -d @/tmp/transfer.json

# ④ 聚合衍生请求（策略3：就高从严升级，预期命中未定义区/差异点）
cat > /tmp/derived.json <<'EOF'
{"@context":["https://w3id.org/dspace/v0.8/context.jsonld","https://w3id.org/tdg/vocab"],"@type":"ContractRequestMessage","consumerPid":"urn:uuid:consumer-computeside","offer":{"@type":"Offer","id":"policy:derived-aggregation-escalation","target":"asset:derived:compute-power-correlation","tdg:operandAssets":["asset:uk-carbon-intensity-48h","asset:owid-gbr-electricity-annual"]},"callbackAddress":"http://localhost:9292/callback"}
EOF
HDR 04_derived_aggregation "http://$P/contract/negotiations" -d @/tmp/derived.json

echo "== 完成。证据目录: $EV/ ==" 
echo "== 注意: ③ 的 agreementId 需从 ②a 响应中取值后重跑该步; 消息体字段以目标版本 DSP spec 为准（本脚本基于 DSP profile 0.8/2024-1 路径占位，目标机按模板实际端点微调） =="
