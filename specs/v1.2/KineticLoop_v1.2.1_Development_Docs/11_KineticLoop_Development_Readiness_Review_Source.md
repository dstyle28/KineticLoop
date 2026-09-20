# KineticLoop v1.2 Development Readiness Review

评审对象：`KineticLoop_v1.2_Development_Docs.zip`。仅审查交付包及其内部对应关系；未改写冻结 Protocol、DB baseline 或其他原文件。

**结论：可以开始开发，但 Project Plan v0.1 不能原样作为完整执行计划。M1 与不依赖争议语义的 M2 工作可以立即启动；Shadow 的持久化/成功语义、概要文档漂移和验收门槛映射应在对应合同、事务与测试实现前关闭。生产自动激活仍不具备条件。**

冻结基线不需要因此整体推翻。主要问题是上层文档如何准确落实冻结语义，以及如何把 roadmap 变成可验收的工作包。

## 1. 实际核验范围

- DOCUMENT_MANIFEST 中 15 个文件的字节数和 SHA256 全部匹配；包内另外一个文件是 manifest 本身。
- Master 中 Protocol、DB baseline、Project Plan 为原文嵌入；PRD、System Design、Tech Spec、ADR、Release Gates 的正文与独立文件一致，标题经过整合。Freeze Review 是独立文件，未整段嵌入 Master。
- 51 个逻辑关系、18 条 invariant、T1–T8、原 34 个验收 ID 在文档与 JSON 间一致。
- 原 34 项按声明的层级拆分，实际包含 **67 个 test-ID × layer 验收义务**，不是运行 34 个任意层级测试即可完成。
- M0–M11 的 JSON 依赖图无环。
- Markdown 定义 31 个 KL 任务 ID；JSON 的 `first_backlog_ids` 仅列出前 18 个，且没有完整 task records。这符合字段名“初始 ID”的含义，但不能称为完整可执行 backlog。
- 包内没有 `protocol_model/` 源码、模型报告、policy fixtures，也没有指向该模型的可取得 commit/tag 与内容摘要。因此此次未独立复跑冻结版模型；589 条调度等数字是包内声明的既有证据，不作为此次新测结果。

机器检查详见 [Package Audit](/Users/davetian/Documents/Codex/2026-09-17/role-objective-principal-ai-native-architect/outputs/KineticLoop_Development_Package_Audit_v1.2.json)。哈希正确证明文件一致，不证明它们相互没有语义冲突。

## 2. 必须修正的问题

### F01 — P0，阻断 Shadow commit/T6 合同：第一条演示路径没有唯一的授权语义

**位置：** Project Plan M7、§9；Technical Spec §23；冻结 DB S38–S40/T6；Protocol §5.3/§6.2。

Plan 要求 `commit SHADOW bundle` 且不产生 production issuance。冻结 DB 却规定：bundle/head 切换、处方、授权、intent 成功同 T6 原子完成；draft/proposal 留在 S34。规划成功也与真实提交绑定。

“没有 production issuance”可以合理地表示“隔离环境产生模拟 A”，也可能被实现为“在用户 active head 上提交 bundle，但跳过 S42”。文档没有选择其一。后者会违反冻结 T6，前者则缺少明确的环境、主体、权限和展示边界。

**具体失败路径：** 开发者为通过 M7，在 LOCAL_SHADOW 下给 CommitBundle 加 `if shadow: skip_authorization`，仍切 S38、更新 execution basis 并置 intent success。此后生产/影子计划共用 head，可能挤掉有效计划或污染累计暴露。反过来，如果为了跑 demo 打开宽松测试 policy，又没有真实用户隔离，就可能把测试授权暴露成可执行建议。

另外，“从未有有效 A → revoke 后仍不可执行”是空洞验证，不能证明撤销有效。

**不改冻结语义的推荐处理：**

- **协议演示：** 在隔离 test database / test subject / TEST_ONLY policy 中运行完整 T6/T7，确实创建模拟 A。先断言模拟 A 有效、START 可成功，再撤销并断言后续资格失效；生产主体不可使用该 A。
- **真实数据 shadow：** 只保存不可执行 proposal/evaluation artifact，不切用户 active bundle/head、不预留或增加真实计划暴露、不产生 production A。影子运行完成不能冒充 live PlanningIntent 的 `FOUND_VALID_PLAN`；使用已有隔离 evaluation 生命周期，或明确提出新的协议变更。
- UI/API 明确 `SHADOW_ONLY / NOT_EXECUTABLE`；不能落入 `AI_GENERATED_CURRENT` 后被误认为可执行。普通 plan retrieval 不混入影子结果。
- 首个协议演示应包含确定性的 Fitness + Demand + Nutrition fixture；M7 先换真实 Fitness，Nutrition 仍可保持类型完整的 fixture，M8 再换真实 Nutrition。不能为了分阶段开发绕过 F/D/N 依赖验证。

如果产品坚持“生产命名空间中的 shadow bundle 也要切 active head / 使用原 intent 成功态”，这属于需要 ADR/兼容性决定的语义选择，不能仅加一个字段解决。

**关闭时点：** KL-014/015 与 KL-045 合同设计前；不阻止 M1。

### F02 — P1，阻断对应事务实现：Technical/System Design 存在安全相关的概要漂移

**位置：** Technical Spec §7（151–160 行）；System Design §11（200–207 行）；冻结 Protocol §2.1a、DB §4.1。

Technical Spec 把“Frozen logical lock order”写成从 user coordination 开始，漏了 T3/T6/T7 前置共享 registry gate。§18 虽然要求检查 SafetyRegistry，但“检查存在”不等于与全局 revoke 正确串行化。

**失败路径：** T6 查到 artifact 未撤销 → T2-GLOBAL 提交 revoke → T6 仅持用户锁提交。每个模块都做了自己的检查，但撤销之后仍成功签发。原冻结协议已经正确禁止这种实现；问题在下游规范。

System Design 的 ledger 图又画成可被读作 `RESERVED → CANCELLED_BEFORE_DISPATCH → DISPATCH_INTENT` 的链，应明确画为互斥分支。按字面实现“取消后再发”会导致预算退回后仍调用 provider。

**修正：** 上层采用同一规范片段或自动生成图，完整标注：T3/T6/T7 registry shared → user；T2-GLOBAL registry exclusive、不取 user；用户 STOP 不依赖 registry。取消与 permit 是 RESERVED 的两条互斥分支。用文档/模型一致性检查阻止再次漂移。

**关闭时点：** KL-015、KL-021、KL-025/026 开始实现前。无需重开已正确的冻结基线。

### F03 — P1，阻断验收框架及 Release Gate 的完整性：34 项清单不能单独代表全部冻结安全要求

**位置：** Acceptance Spec JSON；Release Gates §3；Project Plan KL-005、M3、M11。

Acceptance JSON 只有 E/D/A/W/R 原 34 项，没有 P01–P18；`primary_tables` 中没有 S49–S51。Plan M3 已列出 global revoke 等交错，所以这些要求并非完全遗漏，但没有稳定测试 ID、层级、责任任务及必过状态纳入机器 gate。

Release Gate 写“冻结协议全部实现”在语义上涵盖新增要求；问题是 CI 没法仅凭当前 JSON 证明这句话。若 KL-005 只从该 JSON 生成 tests，可能出现“34 项全绿”，但全局撤销、TTL 传递闭包、READY 写屏障仍没有实际测试。

**修正：**

1. 保留原 34 ID；为 18 个补充边界建立生产验收映射。可沿用 P ID，也可使用新的稳定 requirement IDs；不能直接把模型 PASS 迁成生产 PASS。
2. 为九组交错各分配 ID 和 DC/WF 义务；补入 registry outage、共享 gate 的新鲜读、相关/无关制品撤销、CONTINUE/RESUME、缺 validity、传递 TTL 等必过项。
3. 本冻结版补充的 `effective_at` 语义需要新增用例：过去/未来 effective_at 都不改变 emergency revoke 的提交即失效；事务 rollback 不产生撤销；不改写历史 START。
4. 原 34 项按 67 个 `(test_id, layer)` 跟踪结果。NOT_RUN、SKIPPED 不能等于通过；N/A 必须有受批准的 release scope 理由。
5. Gate 绑定 requirement-set version/hash、代码/迁移/policy/release identity、证据文件与结果，禁止手填一个 `passed=true` 代替证据。

**关闭时点：** KL-005 建测试框架时完成目录；实际测试按 M3/M4/M5…实现，不要求开工前全部通过。

### F04 — P1，计划顺序错误：M10 包含 M3/M7 已经依赖的能力，真实数据保护也不能拖到 M11

**位置：** Project Plan M5/M7/M9/M10/M11；Backlog 中 M10 depends_on M8/M9。

M7 的 DoD 要求 audit/replay；M3 已需 SafetyRegistry；冻结 attempt 绑定精确 model/prompt/tool/runtime 制品。M10 才交付 release registry、固定 evaluation 数据和 replay，意味着 M7 可能先用临时版本、无保留输入的日志或事后选择的测试集运行。这是“基础能力”和“完整 staging 能力”没有拆开。

M5 导入真实 Sheet，M7 向远端模型发 context，M9 接 live providers，但明确 security review 在 M11。可以把正式上线安全审核留到 M11，不能把身份/主体边界、凭据保护、数据外发和日志脱敏的实现也隐含推迟。

**调整：**

- M1：命令/intent correlation、结构化审计接口、配置/secret 分离、synthetic fixtures；固定可复现工具链。
- M2/M3：registry 最小制品登记、schema/policy 版本、主体隔离与管理 capability、replay 写隔离、测试角色不能被 production 路径接受。
- M4：可断言的 revoke/lock/unknown-budget 指标和故障证据，不必先建完整 dashboard。
- M7 之前：固定小型评价集、预先确定判分规则、完整输入/输出及制品绑定、模型拒绝/坏格式/超时案例。质量阈值可在此阶段确定，不必等自动激活；安全负例采用明确拒绝断言。
- 真实 Sheet 导入或真实 context 外发前：数据访问/外发范围与日志留存行为有测试。M11 负责综合复审，不替代早期实现门槛。
- M10 保留 staging、正式 SLO、全面 replay/eval 和 shadow comparison。

### F05 — P1，执行计划尚不完整：Backlog 和 Traceability 更接近目录，未建立任务到证据的对应

**位置：** Project Backlog JSON、DB Traceability JSON、Project Plan §6。

Backlog 有 milestone DAG 和 18 个初始 ID，没有 task 级 dependencies、交付物、DoD、对应 command/transaction/测试或证据路径。Markdown 有 31 个 ID；KL-030–035、KL-040–046 不在该初始列表。无需现在把 M11 的所有任务细化，但 M1/M2 的任务至少应具备执行条件。

DB Traceability JSON 的表项仅含 ID/name/class，另列 invariant 文本和 T1–T8。部分表引用可从 Tx 文字中找到，但缺少显式 table↔invariant↔command↔test↔ticket 的结构化边。相较“有多少张表”，开发 handoff 更需要回答“这个不变量由哪个写入口实施，由哪个测试证明”。

**下一工作包最小字段：**

```text
id, milestone, owner_role, depends_on,
commands, transaction_boundaries, invariant_ids, table_ids,
required_test_layers, deliverables, definition_of_done,
status, evidence_refs
```

并为任务增加进入条件：依赖合同已确定、policy 缺失时行为已定义、测试 oracle 可实现。不要凭任务标题让开发者临时决定权限含义。不要求编造工期；需要排期时再补真实人力和容量。

**关闭时点：** M1/M2 工作包排入实现前；后续里程碑按滚动方式细化。

### F06 — P2，handoff 不可独立复验：模型证据没有绑定到可取得的源码版本

**位置：** Freeze Review §4；Project Plan M0；DOCUMENT_MANIFEST。

Freeze Review 声明本 release 重新跑了 `protocol_model/run_model.py`，包中却没有该路径、运行报告或外部模型源码引用。开发文档包不一定要携带代码，但应能找到并验证它。15 个文档的 SHA 不会自动证明模型测试了这份 frozen spec。

**修正：** 增加 evidence manifest：模型仓库/附件位置、commit/tag、source/report/policy fixture hashes、运行命令/runtime、所测试 protocol hash；保留模型范围限制。M0 拆为规范冻结和证据交接两个状态，不能用前者代替后者。

数个文字引用还指向无数字前缀的文件名，包内实际文件带 04/05/06/07 前缀。给出 stable document ID → 实际文件映射，或修正引用并重新生成 manifest，避免 AI/脚本打开旧文件。

### F07 — P2，路线过宽且依赖分类不足：DDL 顺序和 adapter 完成条件需要收紧

**位置：** Project Plan M2（Program/catalog/config 排第九）、M9/M10；Backlog milestone dependencies。

- M2 的列表是业务实施顺序，不应直接当 migration 的依赖顺序。S01、Manifest、admission 等已经引用 Program/policy/catalog；物理建表需按 FK/引用拓扑，或分阶段创建约束。第一条协议测试不必等 51 个关系的全部领域行为完成，但最小引用根和类型合同要先有。
- M9 将 Hevy、HealthKit bridge、Oura、nutrition、DEXA 放在一个 milestone，M10 强依赖 M9，却没有定义“至少一个来源成功”还是“全部适配器完成”。任一来源/设备接入延迟都可能不必要地阻塞 staging/eval。

**修正：** 先建必要 schema/contract 依赖根，再做最小真实数据库协议切片；其余领域模块按已确定合同补齐。M9 拆成 MVP 必需来源与可选扩展，M10 只依赖 launch scope 内来源。若 V1 确实要求全部来源，就明确该条件并接受相应关键路径成本。

## 3. 建议的 Project Plan v0.2 调整

这是一份执行计划修正建议，不修改冻结权限语义，也不是要求重新扩建架构。

| 阶段 | 核心交付与入口条件 | 可审核退出证据 |
|---|---|---|
| M1 | 工程骨架 + baseline/evidence 导入 + 下一工作包的 typed backlog | 干净 checkout 可启动；模型证据可定位；synthetic/default deny config 测试；67 个原 layer obligations 与新增边界已登记 |
| M2 | command/results、引用根、管理/用户/test 角色边界、物理 schema/事务设计；先关闭 F01/F02 | 每个 command 唯一 owner、锁序、错误码、幂等规则；migration 可重建；明确 shadow 与 test-only 数据去向 |
| M3 | 最小真实 PostgreSQL 协议演示，完整模拟 T6/T7；随后补领域实现 | 有效→START→revoke→拒绝的正/负轨迹；九组 DC、READY 写屏障、TTL、registry 新鲜读；每项有 ID/结果/代码摘要 |
| M4 | worker/reaper/outbox + 故障边界 | 真实进程切断、未知结果预算占用、接管 fencing、ACK 丢失幂等、独立 STOP；不能只 mock 抛异常 |
| M5/M6 | canonical training 与 context 工具 | corrections/dedup/absence dependency/未发布输入测试；真实数据准入前隐私与主体边界检查 |
| M7 | 真实 Fitness + fixture Nutrition；隔离 shadow；最小 release/eval/replay 已具备 | 精确 artifact/input 绑定，质量评价规则，refusal/timeout/bad-output、预算与不混入 active head 证据 |
| M8 | 真实 Nutrition 与跨域修复 | F/D/N 哈希及滚动 envelope；policy 未配置不能绕过 |
| M9 | 明确的 MVP live source 集合；可选来源另行 | 每个必需 adapter 的接收/更正/晚到 fixture 与实际集成证据 |
| M10 | 完整 staging、SLO、eval、shadow comparison | 可定位的 release bundle 与全套 staged evidence |
| M11 | 综合 release review | 所需 gate 全部有证据，非运行即通过；单独做 launch 决策 |

Project Plan §9 的“第一条 demo”必须被提升为 M3 的明确交付和退出条件，不能让它游离于 milestone DAG 之外。

## 4. Development-ready 判断

| 判断范围 | 结论 |
|---|---|
| 冻结架构能否作为开发起点 | YES，保留包内冻结 Protocol/DB 的权威地位 |
| M1、明确边界内的 M2 是否可开工 | YES |
| 当前 Project Plan 是否可原样自动分派并一路实施 | NO，F01–F05 需要纳入对应前置工作包 |
| Shadow T6/T7 合同是否已经可直接编码 | NO，先区分隔离模拟授权与真实数据非执行影子输出 |
| 是否需要再加架构层或全面重做 schema | 当前证据不支持此需求 |
| 是否生产/自动激活 ready | NO；实际 PU/DC/WF/E2E、政策与 release evidence 尚未完成 |

最重要的管理动作是**允许工程开工，同时为尚未定义的执行语义设明确阻断点**。不要用整个项目停工代替边界管理，也不要用“上位规范优先”容忍开发者每天在相互冲突的摘要中猜实现。

## 5. 证据定位

以下行号指向本次 zip 的只读解包副本，未对其内容作任何修改。

- [Project Plan — M2/M3](/Users/davetian/Documents/Codex/2026-09-17/role-objective-principal-ai-native-architect/work/development_docs_v12/06_KineticLoop_Project_Plan_v0.1.md:128)
- [Project Plan — M7/M10/M11](/Users/davetian/Documents/Codex/2026-09-17/role-objective-principal-ai-native-architect/work/development_docs_v12/06_KineticLoop_Project_Plan_v0.1.md:225)
- [Project Plan — 首个演示](/Users/davetian/Documents/Codex/2026-09-17/role-objective-principal-ai-native-architect/work/development_docs_v12/06_KineticLoop_Project_Plan_v0.1.md:387)
- [Technical Spec — 不完整锁序](/Users/davetian/Documents/Codex/2026-09-17/role-objective-principal-ai-native-architect/work/development_docs_v12/03_KineticLoop_Technical_Spec_v1.2_FROZEN.md:149)
- [System Design — ledger 图](/Users/davetian/Documents/Codex/2026-09-17/role-objective-principal-ai-native-architect/work/development_docs_v12/02_KineticLoop_System_Design_v1.2_FROZEN.md:196)
- [Frozen Protocol — registry 协调](/Users/davetian/Documents/Codex/2026-09-17/role-objective-principal-ai-native-architect/work/development_docs_v12/05_KineticLoop_Protocol_v1.2_FROZEN.md:105)
- [Frozen DB — bundle/head 约束](/Users/davetian/Documents/Codex/2026-09-17/role-objective-principal-ai-native-architect/work/development_docs_v12/04_KineticLoop_DB_Schema_Design_v0.2_FROZEN.md:350)
- [Release Gates — 原 34 项要求](/Users/davetian/Documents/Codex/2026-09-17/role-objective-principal-ai-native-architect/work/development_docs_v12/09_KineticLoop_Acceptance_and_Release_Gates_v1.2_FROZEN.md:33)
- [Freeze Review — 模型执行声明](/Users/davetian/Documents/Codex/2026-09-17/role-objective-principal-ai-native-architect/work/development_docs_v12/07_KineticLoop_Protocol_Freeze_Review.md:29)
