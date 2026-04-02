# 地址修复前后对比报告

- 输入文件: `/Users/summer/Downloads/poi_qc_0401tmp_202604021404.csv`
- 输出CSV: `/Users/summer/Documents/bigpoi-qc/skills/BigPoi-verification-qc-V1.1.0/BigPoi-verification-qc-stable/examples/address_fix_compare_20260402_164313.csv`
- 样本总数: 11
- QC状态变化条数: 10
- 地址维度变化条数: 10

## 状态分布

- 原QC: {'unqualified': 1, 'risky': 10}
- 新QC: {'unqualified': 1, 'qualified': 10}
- 原地址状态: {'risk': 11}
- 新地址状态: {'risk': 1, 'pass': 10}

## 变更明细

- [2] 梅云街道办事处: QC risky->qualified; 地址 risk:single_exact_address_support->pass:address_semantic_same_place
- [3] 龙湖镇人民政府: QC risky->qualified; 地址 risk:None->pass:address_supported
- [4] 潮州市湘桥区太平街道办事处: QC risky->qualified; 地址 risk:single_exact_address_support->pass:address_semantic_same_place
- [5] 梅菉街道解放社区居民委员会: QC risky->qualified; 地址 risk:soft_address_match_only->pass:address_semantic_same_place
- [6] 深圳市南山区西丽街道办: QC risky->qualified; 地址 risk:single_exact_address_support->pass:address_semantic_same_place
- [7] 石井街道办事处: QC risky->qualified; 地址 risk:soft_address_match_only->pass:address_semantic_same_place
- [8] 汕尾市人民政府: QC risky->qualified; 地址 risk:soft_address_match_only->pass:address_semantic_same_place
- [9] 金和镇人民政府: QC risky->qualified; 地址 risk:single_exact_address_support->pass:address_semantic_same_place
- [10] 黄埠镇人民政府: QC risky->qualified; 地址 risk:soft_address_match_only->pass:address_semantic_same_place
- [11] 东莞市大岭山镇人民政府: QC risky->qualified; 地址 risk:soft_address_match_only->pass:address_supported
