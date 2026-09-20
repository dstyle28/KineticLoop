# Pre-freeze executable model report

状态：**PASS；NOT FROZEN**。

模型验收 34；新增边界 18；交错场景 9；完整调度 589；负向故障检出 8/8。

所有数字仅指有限状态模型；真实 PostgreSQL / 进程故障 / LLM 调用均为 0。
原验收的生产 PU/DC/WF/E2E 标签保留为 NOT_RUN，不由模拟结果替代。

| 场景 | 完整调度 | 访问前缀 | 死锁 | 违例 |
|---|---:|---:|---:|---:|
| publish_vs_user_revoke | 40 | 216 | 0 | 0 |
| start_vs_user_revoke | 40 | 216 | 0 | 0 |
| cancel_vs_dispatch_intent | 10 | 65 | 0 | 0 |
| lease_takeover_vs_commit_with_clock | 440 | 1995 | 0 | 0 |
| artifact_revoke_vs_issue | 14 | 135 | 0 | 0 |
| artifact_revoke_vs_start | 14 | 135 | 0 | 0 |
| artifact_revoke_vs_publish | 14 | 135 | 0 | 0 |
| factset_seal_vs_input_update | 10 | 65 | 0 | 0 |
| dependency_expiry_vs_start | 7 | 35 | 0 | 0 |

穷举边界：每场景固定 2–3 个 actor、一次命令，guard 与 mutation 合并为原子 APPLY。
不证明任意长度执行、公平性、数据库锁实现或进程崩溃恢复。

详细 Given/When/Then、逐例结果、故障检出、源码 SHA-256 见同目录 model_report.json。

复跑：在 protocol_model 目录执行 `python3 run_model.py`（Python 3.9+，仅标准库）。
