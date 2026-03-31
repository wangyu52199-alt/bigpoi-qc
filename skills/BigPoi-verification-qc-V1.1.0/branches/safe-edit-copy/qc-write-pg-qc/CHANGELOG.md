# CHANGELOG

## [1.3.1] - 2026-03-31

### 文档
- `SKILL.md` 压缩为紧凑版，保留输入契约、查找策略、校验链路、写库映射与安全约束
- 原完整版说明保留为 `SKILL_FULL.md`，用于历史追溯
- `README.md` 新增“版本追溯”入口，统一指向 `SKILL.md / SKILL_FULL.md / CHANGELOG.md`

## [1.3.0] - 2026-03-31

### 新增
- 新增运行时配置文件 `config/qc_runtime.json`，支持固定 `result_dir`
- 支持 `strict_result_dir=true`：忽略外部 `result_dir` 并禁用跨目录恢复搜索

### 调整
- 回库结果候选查找策略收敛为“优先标准目录 + 受约束恢复搜索”
- 多候选时按时间戳与修改时间自动择新，仍无法区分时返回歧义错误
