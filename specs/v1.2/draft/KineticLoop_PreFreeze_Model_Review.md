# KineticLoop — Pre-freeze Model Review

结论：**三个 P0 已写成明确协议并获得有限模型验证；保持 Freeze Candidate。未生成 SQL，未开放自动授权。**

## 本轮交付

- `KineticLoop_v1.2_Protocol_Freeze_Candidate_r2.md`：新的规范评审基线；原 Candidate 保留为历史。
- `KineticLoop_DB_Schema_Design_v0.2.md`：51 个逻辑关系，原 48 个未合并；新增 S49 制品、S50 撤销历史、S51 注册表协调点。
- `KineticLoop_DB_Schema_v0.2_Traceability.json`：18 条 invariant、T1–T8、T2 子命令、34 项原验收与模型证据的对应；含文档和报告 SHA-256。
- `protocol_model/`：可复跑标准库 Python 模型、34 项 GWT fixtures、18 项补充边界、调度枚举、负向校验和默认禁用配置。

## 三个 P0 的处置

| P0 | 现在定义的权限/事务含义 | 获得的模型证据 | 尚未证明 |
|---|---|---|---|
| Factset build→seal | BUILDING/READY 是候选；READY 固定成员和摘要；T2-IN 先接受输入/即时失效，T2-SEAL 独立核验后原子封存及切 head；canonical read 只读 SEALED | P01–P03；seal vs input update；stale seal 不切 head；projection 不推 generation | 实际数据库 READY 写屏障、build 清理、FULL/DELTA 大规模重建和封存复杂度 |
| 全局紧急撤销 | 不可变传递制品依赖 + 追加 revoke；publication/issue/execution 共享 registry gate，全局 revoke 排他；不逐用户更新 epoch；不允许旧 identity 恢复 | P04/P05/P16/P17；revoke vs issue/start/publish；无关撤销不影响 A；相关上游撤销阻断继续资格 | 管理 capability、真实 gate 新鲜读、故障/负载/公平性、跨节点撤销送达 |
| 依赖有效期闭包 | A 截止时间取所有关键依赖期限、政策上限、请求上限、日/session 边界最小值；缺失 deny；TIMELESS 显式批准且可撤销 | P06–P08/P14/P18；逐依赖最短期限；额外字段不能覆盖上限；到期 vs START | 完整证据 freshness policy、真实时钟、DST/时区和临床阈值有效性 |

需要保留的两个实现约束：用户 STOP 不依赖全局 registry 的可用性；Factset seal 不在用户锁内重新计算整个成员集合摘要。模型和 r2 已按此处理。

## 执行结果

`python3 run_model.py`：PASS。

| 检查 | 结果 |
|---|---:|
| 原 34 个验收规格的模型对应案例 | 34 / 34 |
| 新增边界案例 | 18 / 18 |
| 有限交错场景 | 9 / 9 |
| 完整调度 / 访问前缀 | 589 / 2,997 |
| 模型内死锁 / 违例 | 0 / 0 |
| 人为故障变体检出 | 8 / 8 |
| 真实 PostgreSQL / 进程故障测试 / LLM 调用 | 0 / 0 / 0 |

常规 unittest 有 54 个入口：34 + 18 + 交错汇总 + 故障变体汇总。不能把 589 条调度解释成 589 个独立业务需求或无限状态证明。

四组要求的关键交错全部保留，新增五组用于覆盖本轮 P0：artifact revoke vs issue/start/publish、seal vs input update、expiry vs START。调度器枚举固定 2–3 个 actor 的所有可执行步骤顺序；APPLY 内的 guard 与 mutation 假设原子，锁获取/释放与时钟可独立交错。

八个负向变体分别删除用户 epoch、fencing、未封存读取限制、全局撤销、TTL 闭包、未知发送预算保护、反证纳入、未知暴露保留。它们均触发已有断言失败；这说明测试能发现这些指定退化，不代表任意实现缺陷都可检出。

详细逐例结果、GWT、抽象范围、所有调度结果分类和源码摘要在 `protocol_model/reports/model_report.json`；简表在同目录 `model_report.md`。

## 配置是否真实禁用

默认构造器加载 `LOCAL_SHADOW`：production issuance 关闭、progression 关闭、外部调用预算零、fallback 空、离线开始关闭。P15 实际运行该配置，验证预算/签发拒绝及 STOP 仍可执行。

只有测试 helper 显式加载 TEST_ONLY，才能产生模拟授权。所有 tick、额度、时长和组次均为合成模型值；没有填入可用于真实训练的默认数字。配置文件不是生产部署许可。

## Protocol freeze 自审

本轮对三个指定反例给出了可执行 guard 和明确线性化规则。在已枚举的有限范围内，没有发现需要再加架构层才能修复的违例。但以下事项不能被 PASS 覆盖：

1. **新增权限与事务边界仍需评审确认。** SafetyRegistry 是本轮新增 primitive；管理员写权、依赖闭包责任、共享/排他 gate、T2-IN/SEAL/GLOBAL 的独立事务含义写入 r2 后，不能未经审查自动标 FROZEN。
2. **模型不是实现验收。** 34 项生产 PU/DC/WF/E2E 保留 NOT_RUN；R04 只测试环境 guard，A07 只模拟额度耗尽，W01 只模拟命令间断点。没有证明数据库角色隔离、真实队列恢复或真实进程重启安全。
3. **完整领域与 API 合同仍有实现义务。** 真实 admission、全量 session lifecycle、累计暴露对账、general idempotency gateway、管理 capability、完整 policy schema 不是这套模型提供的生产代码。对应模型只覆盖其明确列出的局部语义。
4. **规模要求仍无实测证据。** 单一 registry gate 在 V1 可提供清晰串行化语义，但等待上界、写入优先和吞吐必须由后续 DC/压测验证；不能据此声称百万 DAU 底座已验收。

因此当前 gate 为：模型交付完成；协议评审候选更新；**NOT FROZEN / NO DDL / NO AUTO-ACTIVATION**。下一轮评审可直接围绕 r2 的权限与事务语义及这些执行证据进行，无需重新讨论原有七层架构。

## 复跑与追溯

在 `outputs/protocol_model` 执行 `python3 run_model.py`。在工作区根目录执行 `python3 work/validate_logical_schema_v0_2.py`，验证逻辑映射、模型结果及源码摘要。

原 v0.1 文档与 traceability 未改动。模型报告重新生成会更新时间戳和摘要，因此复跑后需重跑 v0.2 traceability 校验以刷新报告指纹。
