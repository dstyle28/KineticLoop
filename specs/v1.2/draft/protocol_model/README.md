# KineticLoop — Pre-freeze executable protocol model

状态：**模型验证包；Protocol 仍为 Freeze Candidate。无 DDL、无生产服务、无真实 LLM 调用。**

## 运行

Python 3.9+，只使用标准库。在此目录执行：

```bash
python3 run_model.py
python3 -m unittest discover -s tests -v
```

第一条命令校验原 34 个验收 ID / Given / When / Then 与模型 handler 的一一映射，运行模型测试、交错探索及负向校验，生成 `reports/model_report.json` 与 `reports/model_report.md`。失败时退出码非零。报告记录模型、fixture、配置、测试与 runner 的 SHA-256；时间戳随复跑变化。

第二条是常规 unittest 入口；交错和负向校验各占一个测试入口，因此总数与底层调度数量不同。

## 文件

| 文件 | 用途 |
|---|---|
| `kineticloop_model/model.py` | FakeRepository、原子命令、准入/发布/授权/预算/回放模型 |
| `kineticloop_model/interleavings.py` | 固定 actor 与步骤下的完整调度枚举 |
| `fixtures.json` | 原 34 项 GWT、测试层级、handler 和抽象限制 |
| `tests/test_acceptance.py` | 34 个原规格的模型对应案例与 18 个补充边界案例 |
| `tests/test_mutations.py` | 人为删除八个关键 guard/语义，确认已有测试能发现错误 |
| `policies.json` | 默认禁用配置与显式 TEST_ONLY 配置 |
| `run_model.py` | 校验、执行、机器可读结果和人读报告 |

## 三个 P0 的实现落点

1. Factset：BUILDING 可写 candidate；READY 固定 members、member revision 和 digest；T2-SEAL 只重检前沿、epoch、完成凭据后切换 SEALED/current pointer。未 SEALED 不允许 canonical read。失败不切 head，不原地改旧 SEALED。
2. 制品撤销：不可变 artifact dependency closure + 追加撤销事件。publish / issue / executable / START / RESUME 检查传递闭包；CONTINUE 在模型中由 executable 表示。用户 epoch 不必增长，无关制品撤销不使此 A 失效。交错模型给这些准入操作共享 registry gate，给 global revoke 排他 gate；用户 STOP 与预算恢复不依赖该 gate。
3. TTL：记录每项依赖的有效期并取最早到期。Manifest、projection、resolution、policy、日界线、请求上限和传递制品都参与；关键 validity 缺失则拒绝。静态身份的 TIMELESS 必须带显式 policy 与理由，仍可撤销；客户端 extra 字段不能覆盖系统计算的上限。

## 默认安全配置

`ProtocolModel()` 默认 `LOCAL_SHADOW`：自动签发关闭、外部请求预算为零、progression 关闭、fallback 空、离线开始关闭。缺少训练数字不会调用模型补齐。`seeded_model()` 显式选 `TEST_ONLY`；数值单位是虚拟 tick / cost unit，不能作为训练或营养建议。即使测试开关允许产生模拟 issuance，也不存在 production issuance 路径。

## 证据边界

本包验证有限的协议反例；原 34 项规格均有模型对应案例，**不等于原验收的生产实现全部完成**。逐例 `model_scope` 保留在 fixture/report 内，原 PU/DC/WF/E2E 实现测试仍为 NOT_RUN。

- 所有命令假设由可信服务入口调用。缺少真实认证、跨主体隔离、API 契约、数据库角色和不可变写权限；R04 只验证环境拒绝，不能证明存储隔离。
- `@atomic` 用 deepcopy/rollback 模拟不可分割命令；其原子性是前提。交错枚举分开 observation、registry lock、user lock、APPLY 与 unlock，但不展开 SQL 语句。没有验证真实数据库隔离、写偏差、锁公平性或进程内存恢复。
- Factset completion 在模型中算 digest；seal 只比对完成凭据。全量 invariant 扫描是测试 oracle，不是生产事务算法或复杂度保证。生产 READY 写入屏障与常数规模封存检查仍需数据库验证。
- 原始抽取用结构化字段代替 NLP；success/credit、事件关联和风险入口是合成测试输入。模型不提供训练证据准入标准，不实现完整 Blueprint、滚动 envelope、实际执行替换计划暴露的计算。
- 模型对 accepted fact 保守推进用户 epoch；生产 NON_INVALIDATING 分类和细粒度依赖必须另行验证。projection reuse 只模拟一个运动的输入签名。
- Replay 检验 known-at 选择和 release 身份区分，不执行真实 release、历史索引、文件缺失恢复或完整双时间数据库。
- WF 案例在命令边界设置断点、推进虚拟时钟并运行 reaper；没有杀死实际 worker。模拟 transport 每 reservation 只发一次是适配器契约，不是对 provider exactly-once 的保证。结果未知预留不退回。
- 只有单主体和有限 actor、一次命令的调度枚举。没有做随机长期状态序列、无限状态证明、百万用户压测、registry 网络故障、客户端撤销送达或 UI 验证。
- Registry 管理员权限、缺失配置的完整 schema 校验、真实故障码到 API 的映射仍需实现。全局 reader gate 的吞吐、撤销优先级与锁等待上界未测量。

Freeze review 应据此评估权限含义与事务边界；不能从 PASS 自动推出 FROZEN 或可自动激活。
