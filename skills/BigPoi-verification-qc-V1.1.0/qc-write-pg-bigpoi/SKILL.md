---
name: bigpoi-verification-qc-write
version: 1.0.0
description: 将 POI 质检完成的结果（包括质检结论、评分、风险标识、统计标记）更新回 PostgreSQL 数据库，完成质检流程的最后一个环节。
---

# 大 POI 质检结果写入子技能

## 技能目标

`bigpoi-verification-qc-write` 是大 POI 核实质检流程中的**数据持久化与状态转变型子 Skill**，负责将质检完成的 POI 数据及其关键信息（质检结论、评分、风险标识、统计标记）持久化写入 PostgreSQL 数据库，完成质检流程的最后一个环节。

本技能的核心目标是：

* **结果持久化**：将质检决策原子性写入数据库，确保数据一致性
* **状态转变**：将 POI 的 `quality_status` 从 `质检中` 转变为 `已质检`
* **信息完整**：同时更新质检状态、质检结论、评分、详细结果及统计标记等多个字段
* **幂等安全**：支持重试机制，同一数据重复更新不会产生副作用
* **时间戳记录**：自动记录更新时间，支持审计追溯

---

## 技能边界

### 技能必须执行

* 接收来自上游质检 Skill 的：
  * POI_QC 的 `id`（主键）
  * `quality_status`：更新为 `已质检`
  * `qc_status`：质检结论（`qualified` / `risky` / `unqualified`）
  * `qc_score`：质检评分（0-100）
  * `qc_result`：完整的质检结果对象（JSON）
* 以 `id` 为主键进行精确更新（更新 `poi_qc` 表）
* 从 `qc_result` 中提取统计标记字段，同时更新：
  * `has_risk`：是否有风险
  * `is_qualified`：是否合格
  * `is_auto_approvable`：是否可自动审批
  * `is_manual_required`：是否需要人工处理
  * `downgrade_issue_type`：降级问题类型
  * `downgrade_status`：降级维度状态
  * `is_downgrade_consistent`：降级一致性
* 在单一事务中完成全部字段的原子性更新
* 自动记录 `updatetime` 为当前时间
* 返回更新是否成功的状态信息

### 本技能不处理的场景

* 部分字段更新失败时，不执行降级更新（全部提交或全部回滚）
* 修改除上述字段以外的其他字段
* 对不存在的 POI_QC id 进行插入操作（仅更新现有记录）
* 生成或修改 `qc_result` 的内容（仅存储上游输入）
* 处理数据库连接失败导致的重试逻辑（上游Skill需提供容错）

---

## 输入与输出

### 输入语义（Input）

接收来自质检流程的完整质检结果数据：

```json
{
  "id": "QC_123",
  "quality_status": "已质检",
  "qc_status": "qualified",
  "qc_score": 95,
  "qc_result": {
    "qc_status": "qualified",
    "qc_score": 95,
    "has_risk": false,
    "risk_dims": [],
    "triggered_rules": [],
    "dimension_results": {
      "existence": {
        "status": "pass",
        "risk_level": "none",
        "explanation": "POI 存在性通过质检，所有证据一致",
        "confidence": 0.95,
        "related_rules": [],
        "evidence": []
      },
      "name": {
        "status": "pass",
        "risk_level": "none",
        "explanation": "POI 名称与多个权威证据源一致，标准化处理合理",
        "confidence": 0.92,
        "related_rules": ["RULE_NAME_001"],
        "evidence": []
      },
      "location": {
        "status": "pass",
        "risk_level": "none",
        "explanation": "POI 位置与证据数据相符，偏离距离 < 50米",
        "confidence": 0.98,
        "related_rules": [],
        "evidence": []
      },
      "category": {
        "status": "pass",
        "risk_level": "none",
        "explanation": "POI 分类与证据数据一致，与行业标准分类体系一致",
        "confidence": 0.90,
        "related_rules": [],
        "evidence": []
      },
      "administrative": {
        "status": "pass",
        "risk_level": "none",
        "explanation": "POI 行政区与地理位置一致，与地址信息匹配",
        "confidence": 0.88,
        "related_rules": [],
        "evidence": []
      },
      "downgrade": {
        "status": "pass",
        "risk_level": "none",
        "explanation": "所有维度通过质检，整体置信度 >= 0.80，无需人工降级",
        "confidence": 0.95,
        "related_rules": [],
        "evidence": []
      },
      "downgrade_consistency": {
        "status": "pass",
        "risk_level": "none",
        "explanation": "上游降级决策合理。QC 独立判断不需要降级，上游系统也未进行降级，两者一致",
        "is_consistent": true,
        "issue_type": "consistent",
        "qc_downgrade_status": "pass",
        "upstream_downgrade_status": "not_downgraded",
        "upstream_downgrade_reason": null,
        "upstream_downgrade_reason_code": null,
        "confidence": 0.93,
        "related_rules": [],
        "evidence": []
      }
    },
    "explanation": "所有维度质检通过，无质量风险，可直接采纳",
    "statistics_flags": {
      "is_qualified": true,
      "is_auto_approvable": true,
      "is_manual_required": false,
      "downgrade_issue_type": "consistent"
    }
  }
}
```

### 输出语义（Output）

成功时返回更新状态：

```json
{
  "success": true,
  "id": "QC_123",
  "message": "POI 质检结果已成功更新",
  "updated_fields": [
    "quality_status", "qc_status", "qc_score", "qc_result",
    "has_risk", "is_qualified", "is_auto_approvable", "is_manual_required",
    "downgrade_issue_type", "downgrade_status", "is_downgrade_consistent",
    "updatetime"
  ],
  "updatetime": "2026-02-27T10:45:00Z"
}
```

失败时返回错误信息：

```json
{
  "success": false,
  "id": "QC_123",
  "error": "数据库连接失败：...",
  "error_type": "Exception"
}
```

---

## 质检结果定义

### 质检结论类型

| 结论值 | 说明 | 处理方式 |
|--------|------|---------|
| `qualified` | POI 数据质检通过，无质量问题 | 直接入库，后续不再处理 |
| `risky` | 数据存在轻微风险或不确定性 | 转为风险监控流程 |
| `unqualified` | 数据存在明确质量问题，不合格 | 转为人工复核流程 |

### qc_status 字段说明

| 值 | 说明 |
|---|---|
| `qualified` | 质检通过：所有维度为 pass，无任何风险 |
| `risky` | 质检有风险：存在 risk 维度，但无 fail 维度 |
| `unqualified` | 质检不通过：存在 fail 维度 |

### qc_score 字段说明

| 范围 | 说明 | 计算规则 |
|---|---|---|
| 0-100 | 质检评分 | 每个 pass 维度 10 分；每个 risk 维度按风险等级扣分（high: -6, medium: -3, low: -1）；每个 fail 维度 0 分；最终分数 = 所有维度得分之和 / 60 × 100 |

### 统计标记字段说明

| 字段 | 类型 | 说明 | 来源 |
|------|------|------|------|
| `has_risk` | BOOLEAN | 是否有风险（包含 risk 或 fail 维度） | qc_result.has_risk |
| `is_qualified` | BOOLEAN | 是否合格（qc_status == qualified） | qc_result.statistics_flags.is_qualified |
| `is_auto_approvable` | BOOLEAN | 是否可自动审批（qualified 且 downgrade == pass） | qc_result.statistics_flags.is_auto_approvable |
| `is_manual_required` | BOOLEAN | 是否需要人工处理（!= qualified 或降级不一致） | qc_result.statistics_flags.is_manual_required |
| `downgrade_issue_type` | VARCHAR | 降级问题类型（consistent / missed_downgrade / unnecessary_downgrade） | qc_result.statistics_flags.downgrade_issue_type |
| `downgrade_status` | VARCHAR | 降级维度的质检状态（pass / risk / fail） | qc_result.dimension_results.downgrade.status |
| `is_downgrade_consistent` | BOOLEAN | 降级一致性维度的一致性判断 | qc_result.dimension_results.downgrade_consistency.is_consistent |

### qc_result 字段结构

```json
{
  "qc_status": "qualified",
  "qc_score": 95,
  "has_risk": false,
  "risk_dims": [],
  "triggered_rules": [],
  "dimension_results": {
    "existence": {
      "status": "pass",
      "risk_level": "none",
      "explanation": "POI 存在性通过质检，所有证据一致",
      "confidence": 0.95,
      "related_rules": [],
      "evidence": []
    },
    "name": {
      "status": "pass",
      "risk_level": "none",
      "explanation": "POI 名称与多个权威证据源一致，标准化处理合理",
      "confidence": 0.92,
      "related_rules": ["RULE_NAME_001"],
      "evidence": []
    },
    "location": {
      "status": "pass",
      "risk_level": "none",
      "explanation": "POI 位置与证据数据相符，偏离距离 < 50米",
      "confidence": 0.98,
      "related_rules": [],
      "evidence": []
    },
    "category": {
      "status": "pass",
      "risk_level": "none",
      "explanation": "POI 分类与证据数据一致，与行业标准分类体系一致",
      "confidence": 0.90,
      "related_rules": [],
      "evidence": []
    },
    "administrative": {
      "status": "pass",
      "risk_level": "none",
      "explanation": "POI 行政区与地理位置一致，与地址信息匹配",
      "confidence": 0.88,
      "related_rules": [],
      "evidence": []
    },
    "downgrade": {
      "status": "pass",
      "risk_level": "none",
      "explanation": "所有维度通过质检，整体置信度 >= 0.80，无需人工降级",
      "confidence": 0.95,
      "related_rules": [],
      "evidence": []
    },
    "downgrade_consistency": {
      "status": "pass",
      "risk_level": "none",
      "explanation": "上游降级决策合理。QC 独立判断不需要降级，上游系统也未进行降级，两者一致",
      "is_consistent": true,
      "issue_type": "consistent",
      "qc_downgrade_status": "pass",
      "upstream_downgrade_status": "not_downgraded",
      "upstream_downgrade_reason": null,
      "upstream_downgrade_reason_code": null,
      "confidence": 0.93,
      "related_rules": [],
      "evidence": []
    }
  },
  "explanation": "所有维度质检通过，无质量风险，可直接采纳",
  "statistics_flags": {
    "is_qualified": true,
    "is_auto_approvable": true,
    "is_manual_required": false,
    "downgrade_issue_type": "consistent"
  }
}
```

---

## 数据库表说明

### poi_qc 表（质检数据表，写入目标表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | 质检记录唯一标识（主键） |
| `poi_id` | VARCHAR | POI 标识 |
| `batch_id` | VARCHAR | 批次ID |
| `quality_status` | VARCHAR | 质检状态（待质检、质检中、已质检） |
| `qc_status` | VARCHAR | 质检结论（qualified、risky、unqualified） |
| `qc_score` | INTEGER | 质检评分（0-100） |
| `qc_result` | JSONB | 完整质检结果 |
| `has_risk` | BOOLEAN | 是否有风险 |
| `is_qualified` | BOOLEAN | 是否合格 |
| `is_auto_approvable` | BOOLEAN | 是否可自动审批 |
| `is_manual_required` | BOOLEAN | 是否需要人工处理 |
| `downgrade_issue_type` | VARCHAR | 降级问题类型 |
| `downgrade_status` | VARCHAR | 降级维度状态 |
| `is_downgrade_consistent` | BOOLEAN | 降级一致性 |
| `name` | VARCHAR | POI 名称 |
| `address` | VARCHAR | POI 地址 |
| `x_coord` | NUMERIC | POI 经度 |
| `y_coord` | NUMERIC | POI 纬度 |
| `poi_type` | VARCHAR | POI 类型 |
| `city` | VARCHAR | POI 城市 |
| `existence` | BOOLEAN | 是否存在 |
| `createtime` | TIMESTAMP | 创建时间 |
| `updatetime` | TIMESTAMP | 更新时间 |

---

## 执行逻辑

### 工作流程

```
开始
  ├─ 接收质检完成的 POI 数据
  ├─ 验证输入数据的必要字段
  ├─ 连接 PostgreSQL 数据库
  ├─ 从 qc_result 中提取统计标记字段
  ├─ 在事务中执行 UPDATE 操作（更新 poi_qc 表）：
  │   ├─ 设置 quality_status = '已质检'
  │   ├─ 设置 qc_status = 质检结论
  │   ├─ 设置 qc_score = 质检评分
  │   ├─ 设置 qc_result = JSON 对象
  │   ├─ 设置统计标记字段：
  │   │   ├─ has_risk
  │   │   ├─ is_qualified
  │   │   ├─ is_auto_approvable
  │   │   ├─ is_manual_required
  │   │   ├─ downgrade_issue_type
  │   │   ├─ downgrade_status
  │   │   └─ is_downgrade_consistent
  │   └─ 设置 updatetime = 当前时间
  ├─ 提交事务
  └─ 返回更新成功状态
结束
```

### 关键设计点

1. **原子性操作**：所有字段在单一 UPDATE 语句中更新，保证一致性
2. **JSON 验证**：qc_result 必须为有效的 JSON 格式，符合 qc_result.schema.json
3. **统计提取**：自动从 qc_result 中提取统计标记字段，同步更新表列
4. **幂等安全**：重复更新同一 POI 不会产生副作用
5. **时间戳自动**：updatetime 自动设置为当前时间
6. **事务保证**：任何字段更新失败都会全部回滚
7. **状态转变清晰**：质检中 → 已质检

---

## 依赖

* Python >= 3.8
* psycopg2：PostgreSQL 数据库驱动
* PyYAML：YAML 配置文件解析
* PostgreSQL 数据库（big_poi）

---

## 配置

数据库连接参数定义在 `config/db_config.yaml` 中，包含：

* `host`：数据库服务器 IP
* `port`：PostgreSQL 端口
* `database`：数据库名称
* `user`：用户名
* `password`：密码

---
