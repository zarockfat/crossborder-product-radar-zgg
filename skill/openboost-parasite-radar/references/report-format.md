# 离线机会卡格式

用真实数据生成 JSON，再渲染成 HTML。下面仅为结构示例，不能作为真实选品报告；所有文字与 ID 都需替换为当前调查结果。

```json
{
  "title": "宠物用品 · 跨境大卖选品雷达",
  "market": "美国",
  "updated_at": "带时区的生成时间",
  "scope": "小样本探索；接口数据截至日期；调用范围",
  "verdict": "本轮结论及最大限制",
  "hosts": [{"id":"H1","name":"真实商品名","metrics":["近30天销量及其口径"],"evidence":["E01"]}],
  "opportunities": [{
    "id":"O1","name":"候选配件","status":"待验证","host_id":"H1",
    "pain":"有原文证据的痛点，或明确标为未证实假设",
    "hypothesis":"拟解决的问题与最小产品版本",
    "support":[{"text":"支持判断","evidence":["E01"]}],
    "against":[{"text":"反对判断","evidence":["E02"]}],
    "unknowns":["缺口"],"patent":"未查询/受限/已查询及线索，不等于法律放行",
    "test":"最小验证实验与停止条件；阈值为预先设定的实验假设",
    "economics":null
  }],
  "evidence":[{
    "id":"E01","tool":"真实工具名","source_id":"商品ID/ASIN/关键词",
    "retrieved_at":"API采集时间","summary":"此证据支持什么，不支持什么",
    "excerpt":"短摘录或原始字段值，不编造引文",
    "raw_file":"raw/E01.json","pointer":"/payload/data/records/0",
    "url":"https://真实来源地址"
  }]
}
```

status 仅用：`可进入低成本验证`、`待验证`、`淘汰`。可以没有 opportunities，不能为凑数捏造。

证据 ID 必须唯一，引用必须存在；raw_file 必须是报告目录内实际 JSON，pointer 为 RFC 6901 JSON Pointer，脚本会校验可解析。每条证据都包含工具、采集时间、来源ID与短摘录。网页锚点打开证据，文件链接打开原始 JSON；报告中不展示账户资料。url 可省略，不得推造商品地址。

economics 无成本假设时为 null。需要交互成本面板时用：
```json
{"currency":"USD","sale_price":19.99,"fee_pct":15,"fulfillment":4,"ad_cost":3,"return_reserve":1,"target_margin_pct":20,"assumptions":"全部为测算假设；未取得供应商报价或平台费率确认"}
```

公式：采购及头程可承受上限 = 售价 × (1 − 平台费率 − 目标贡献利润率) − 履约 − 广告 − 售后预留。所有金额同币种、按每售出一件分摊。未包含税费、固定费用等，须在 assumptions 中说明；这是用户假设下的单位经济测算，不是实际利润。上限小于0时显示该组假设不可行。售价必须为正数，比例0–100，其余非负。

生成后验证：每个卡片引用、反证和缺口能展开；筛选可用；成本输入变动会更新结果；窄屏无横向溢出。不要在交付 ZIP 内夹带测试账号文件或本机密钥。
