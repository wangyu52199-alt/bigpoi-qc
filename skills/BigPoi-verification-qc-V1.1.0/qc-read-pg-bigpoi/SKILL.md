---
name: bigpoi-verification-qc-read
version: 1.0.0
description: 从 PostgreSQL BigPOI 数据库中读取待质检的 POI 质检数据，检查质检状态，并返回统计信息与待处理数据。
---

# 大 POI 质检数据读库子技能

## 技能目标

`bigpoi-verification-qc-read` 是大 POI 核实质检流程中的**数据获取与状态管理型子 Skill**，负责从 PostgreSQL 数据库中智能读取 POI 质检数据，进行状态检查与智能调度，确保质检流程有序进行。

本技能的核心目标是：

* **智能状态检查**：检测当前是否存在'质检中'的数据，若存在则跳过本次处理，避免并发冲突
* **单条数据获取**：若无'质检中'数据，获取一条待质检的数据作为本轮质检目标
* **原子性状态更新**：将选中的质检数据状态原子性地更新为'质检中'，防止重复处理
* **完整数据关联**：同时读取该 POI 的所有相关数据，包括质检数据、证据信息、上游决策信息
* **统计维度输出**：同时输出各质检状态的数据统计，支持流程监控与决策

---

## 技能边界

### 技能必须执行

* 连接 PostgreSQL 数据库（big_poi）并执行查询操作
* 从 `poi_qc` 表读取质检数据，根据 quality_status 字段进行状态检查：
  * 统计 quality_status='质检中' 的数据数量
  * 统计 quality_status='已质检' 的数据数量
  * 统计其他状态（待质检）的数据数量
  * 检测是否存在'质检中'的数据
* 若不存在'质检中'数据，获取单条待质检的数据（quality_status 不为'质检中'和'已质检'）
* 原子性地将该数据的 quality_status 更新为'质检中'
* 从关联的 `poi_verified` 表读取证据记录和核实详情（JSON 字段）
* 完整读取该 POI 的所有相关数据（record + evidence_data + upstream_decision）
* 返回包含统计信息与待处理完整数据的结构化 JSON 响应

### 本技能不处理的场景

* 数据库中不存在任何待质检数据时，仍需正常返回，仅不包含'need_qc'字段
* 执行任何修改 qc_result、qc_status 等其他字段的操作
* 直接删除或强制更新为其他状态的操作
* 处理数据库连接失败导致的重试逻辑（上游Skill需提供容错）

---

## 输入与输出

### 输入

无特定输入参数要求，skill 直接连接数据库执行操作。

### 输出（JSON 格式）

```json
{
  "qc_checking_count": 0,
  "qc_completed_count": 5,
  "pending_qc_count": 100,
  "need_qc": {
    "read_metadata": {
      "timestamp": "2026-02-27T10:30:00Z",
      "data_source": "PostgreSQL",
      "record_id": "QC_123",
      "read_status": "success",
      "status_update": {
        "updated": true,
        "previous_quality_status": null,
        "current_quality_status": "质检中",
        "update_timestamp": "2026-02-27T10:30:00Z"
      }
    },
    "record": {
      "id": "QC_123",
      "poi_id": "POI_456",
      "batch_id": "BATCH_001",
      "verify_status": "已核实",
      "quality_status": "质检中",
      "name": "XX医院",
      "address": "武汉市武昌区中山路123号",
      "x_coord": 123.2222,
      "y_coord": 65.9999,
      "poi_type": "医院",
      "city": "武汉市",
      "existence": true
    },
    "evidence_data": [
      {
        "evidence_id": "EV_001",
        "source": {
          "source_id": "baidu",
          "source_name": "百度地图",
          "source_type": "地图类"
        },
        "data": {
          "name": "XX医院",
          "address": "武汉市武昌区中山路123号",
          "x_coord": 123.2222,
          "y_coord": 65.9999,
          "poi_type": "医院",
          "city": "武汉市"
        },
        "verification": {
          "is_valid": true,
          "confidence": 0.95,
          "verification_time": "2026-02-27T10:20:00Z"
        },
        "matching": {
          "name_similarity": 0.98,
          "location_distance": 15,
          "category_match": 0.95,
          "is_match": true
        }
      }
    ],
    "upstream_decision": {
      "overall": {
        "status": "已核实",
        "confidence": 0.92,
        "action": "approve",
        "summary": "多维度核实通过"
      },
      "dimensions": {
        "existence": "pass",
        "name": "pass",
        "location": "pass",
        "category": "pass",
        "administrative": "pass"
      },
      "downgrade_info": {
        "is_downgraded": false,
        "reason_code": null,
        "reason_description": null,
        "trigger_conditions": null,
        "recommendation": null
      }
    }
  }
}
```

**输出字段说明：**

* `qc_checking_count`：`poi_qc` 表中 quality_status='质检中' 的数据数量
* `qc_completed_count`：`poi_qc` 表中 quality_status='已质检' 的数据数量
* `pending_qc_count`：`poi_qc` 表中其他状态（待质检）的数据数量
* `need_qc`：本次待处理的单条质检数据对象（若不存在则省略此字段）
  * `read_metadata`：读库操作元数据
    * `timestamp`：读库时间戳
    * `data_source`：数据来源标识
    * `record_id`：读取的记录ID（poi_qc 表的 id）
    * `read_status`：读库状态（success/partial/failed）
    * `status_update`：质检状态更新信息
  * `record`：POI 质检数据（从 poi_qc 表读取）
  * `evidence_data`：所有相关的证据数据列表（从 poi_verified 表的 evidence_record 字段解析）
  * `upstream_decision`：上游核实系统的决策信息（从 poi_verified 表的 verify_info 字段读取）

---

## 数据库表说明

### poi_qc 表（质检数据表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | 质检记录唯一标识（主键） |
| `poi_id` | VARCHAR | POI 标识（关联 poi_verified_test 表） |
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

### poi_verified 表（核实成果表，读取关联数据）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR | POI 标识（主键，与 poi_qc 的 poi_id 关联） |
| `evidence_record` | JSONB | 证据记录（包含 evidence_collection_summary.evidence_list 数组） |
| `verify_info` | JSONB | 核实详情（包含各维度的核实结果） |

---

## 执行逻辑

### 工作流程

```
开始
  ├─ 连接 PostgreSQL 数据库
  ├─ 从 poi_qc 表统计各状态数量
  ├─ 检查是否存在 quality_status='质检中' 的数据？
  │   ├─ 是 → 返回统计信息，不获取待处理数据
  │   └─ 否 → 继续
  ├─ 从 poi_qc 表获取一条待质检数据
  ├─ 判断是否存在待质检数据？
  │   ├─ 是 → 继续
  │   └─ 否 → 返回仅含统计信息的结果
  ├─ 原子性更新该条数据的 quality_status 为'质检中'
  ├─ 读取该 POI 的完整关联数据：
  │   ├─ record（poi_qc 表的核实数据）
  │   ├─ evidence_data（poi_verified 表的 evidence_record 字段）
  │   └─ upstream_decision（poi_verified 表的 verify_info 字段）
  └─ 返回统计信息与完整待处理数据
结束
```

### 关键设计点

1. **状态优先级**：质检中 > 待质检，防止并发冲突
2. **原子性操作**：数据获取与状态更新在单一事务中完成
3. **单条限制**：每次只返回一条待质检数据，避免大量批处理导致的锁定
4. **完整关联**：同时读取多个表的数据，确保质检技能获得完整信息
5. **元数据记录**：记录读库操作的完整上下文，支持审计追溯
6. **JSON解析**：从 poi_verified 的 JSON 字段中解析证据和决策数据

---

## 依赖

* Python >= 3.8
* psycopg2：PostgreSQL 数据库驱动
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
