# OpenBoost 接口与取证

## 调用与错误处理

脚本路径均相对于 skill 目录；输出写到用户指定的结果目录。

```sh
python3 scripts/openboost.py schema tt_commodity_info_list
python3 scripts/openboost.py schema tt_commodity_info_list --live
python3 scripts/openboost.py call tt_commodity_info_list --args /absolute/path/args.json --out /absolute/path/raw/E01.json
```

脚本仅允许本 skill 用到的只读工具，拒绝重定向，默认超时 45 秒，不自动重试付费请求，不自动执行服务端内容。需要更长任务时优先挂载的 MCP 工具。

`result` 保留原始 MCP 结果；`payload` 把 content.text 中多层 JSON 字符串展开。先确认 isError、业务 success/code/msg 和 data；HTTP 200 或 isError=false 不保证业务成功。不同业务成功码可能是字符串 `0` 或数字 `1`，按返回的 success、说明和字段联合判断，不写统一 code==0 规则。

401/403、套餐不足：停止该模块并记录；不自行购买或不断重试。空记录：改一次更宽的关键词或同义词，仍空则标记缺证，不能叫蓝海。必填参数错误：核对 live schema 后修正一次。网络超时：保留任务状态，不假设请求未扣额度；不自动重试。

## 核心路由

| 阶段 | 工具 | 已核对的关键约束 |
|---|---|---|
| 账号 | account_info | 生效套餐看 status/日期；过期试用有余额也不代表可用。账户输出不进入报告。 |
| TT 候选 | tt_commodity_info_list | countryRegion；dataPeriod=last30d/last7d；size≤30；commodityName 会消耗搜索次数；salesQoqDesc 仅适用指定周期。 |
| TT 详情/趋势 | tt_commodity_detail / tt_commodity_sales_trend | commodityId 与 countryRegion；趋势优先级 pastMonth > pastDays > month，选择一种。 |
| 内容/达人 | tt_video_info_list / tt_expert_fans_analyze | 按 commodityId 查询；视频 adSource=0/1 是投流标记，不能证明无其他流量影响；达人档位数量与商品总达人数口径可能不同。 |
| TT 评论 | tt_commodity_voice_read / tt_commodity_voice_analyze | 原文 countryRegion 必须中文，如美国；size≤10；日期起止成对；摘要可能为空。 |
| AMZ 匹配 | amz_product_competitor / amz_sku_query | 美国 webSiteId="1"；竞品 keyword、size≤100；详情参数 skuId，不是 asin。 |
| AMZ 评论 | amz_review_query | skuId，webSiteId；size≤10，current 从1开始；按新到旧，不是低星优先。 |
| 搜索验证 | amz_keyword_miner / amz_keyword_research_trends | keyword 种子词，站点；矿工接口默认最新可用分区，不能称今日搜索量；趋势查实际月度。 |
| 配套关联 | amz_traffic_listing_page | asinList 数组≤20；relations 必填数组。fbt=组合购买，bab=买了又买，vav=看了又看，sp=广告。各种关联均不是因果/转化率。 |
| 季节排除 | amz_google_trends | 仅需要时查；兴趣指数不等于搜索次数或销售额。 |
| 专利图片 | patent_image_search_single | url 为已公开商品图；model=1、patent_type=D 可做外观相似检索；country=["US"] 数组；limit 从3开始。 |
| 专利结构 | patent_semantic_search | 按实际 schema 填技术描述，建议≥200字；语义相似不代表权项覆盖。 |
| 专利核查 | patent_legal_status / patent_claim_data | patent_id/patent_number 至少一个；保存状态更新日；不要直接推断可自由实施。 |

完整参数以 `tool-schemas.json` 中该工具 inputSchema 为起点、实时 schema 为准。字段类型有描述/JSON schema 不一致时优先 live schema，业务仍拒绝则记录具体问题，不遍历猜枚举。

## 可直接使用的小样本参数

TT 候选：
```json
{"countryRegion":"美国","commodityName":"pet feeder","dataPeriod":"last30d","orderType":"salesDesc","size":3,"current":1}
```

Amazon 补位产品检索（词来自痛点假设，不意味着已发现需求）：
```json
{"webSiteId":"1","keyword":"pet feeder mat","size":3,"page":1}
```

关键词：
```json
{"webSiteId":"1","keyword":"pet feeder mat","size":5,"page":1}
```

## 必须保留的数据区别

- 商品价格可能是当前最低变体价；不能用它乘历史销量冒充历史 GMV。
- 近30天汇总与返回的每日点可能不同步；保留两者窗口，差异未查清不相减推算。
- TT 达人数累计值不等于当期有成交达人数；关键词点击集中度不等于销售集中度。
- 同关键词跨平台是类目交叉验证，不代表同一用户从 TikTok 流向 Amazon。
- 当前检索样本没有竞品不等于市场没有竞品；数据采样只支持样本范围的判断。
- 每条量化结论注明来源字段、站点、日期、分母。模型生成的产品方案、测品阈值和成本假设分别标为推断/实验/假设。
- 不调用 `amz_amazon_seeds_reviews_v3` 补齐演示：目录注明单次200调用量、约五分钟后查询；需要时独立说明成本并取得该额外采集授权。
