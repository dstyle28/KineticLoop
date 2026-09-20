# KineticLoop v1.2 — Protocol Freeze Candidate

状态：**规范草案 / Freeze Candidate，未冻结**  
范围：五个协议的状态机、事务边界、故障语义与自动激活验收。  
依据：v1.1 Review Package，以及本轮已接受的架构修正。  
交付边界：本文件定义协议，不定义 PostgreSQL DDL，不声称实现或测试已完成。

## 0. 规范约定与冻结条件

本文 MUST / MUST NOT 表示不可违反的协议要求；SHOULD 表示可以经 ADR 说明理由后替换的建议。所有 ID、版本、时间与授权身份由服务端绑定，模型回显值不产生权限。

协议保证的是证据使用、状态一致性、行动准入和故障有界；不把符合策略等同于医学安全，不把可重复计算等同于经验事实。

AI 继续负责 modality、sequence re-entry、exercise selection、fatigue interpretation、progression proposal、substitution 与 daily nutrition reasoning。代码负责证据资格、证据义务、策略限制、执行授权与状态迁移。

### 0.1 版本变化纪律

- 修改本协议语义需要新 protocol version 与兼容性决定。
- Admission、mapping、projection engine、constraint、authorization、fallback、prompt 等执行版本 MUST 可定位到不可变制品或其内容摘要。
- “不可变”表示禁止原地重写审计历史，不表示无限期保存健康数据。保留、删除和脱敏按明确政策执行；删除导致历史不可复现时 MUST 显示证据缺失，不得编造重建结果。
- 本文的主体边界都包含 user/tenant scope；同一 hash、exercise ID 或日期不得绕过主体隔离。

### 0.2 状态轴必须分开

| 对象 | 负责表达 | 不负责表达 |
|---|---|---|
| Evidence / Assertion | 来源陈述与候选解释 | 自动执行权限 |
| AdmissionDecision | 某证据在特定用途下的资格 | 普遍真实性或医学诊断 |
| DecisionManifest | 原子发布的决策视图 | 当前仍可执行 |
| PlanningIntent / Attempt | 搜索目标、预算与运行进度 | 已批准行动 |
| PrescriptionRevision | 不可变建议内容 | 授权是否有效 |
| AuthorizationIssuance | 一次有条件、有限期的授权 | 永久有效资格 |
| Execution | 实际开始、继续、停止与完成 | 计划必然已执行 |

### 0.3 两个协调计数器

`decision_generation` 只在 DecisionManifest 原子发布时递增。

`authorization_epoch` 是用户级、单调递增的执行失效屏障。它在保护性暂停、停止命令、相关证据撤回、限制变化、授权政策切换等被定义为失效事件的事务中递增。它不依赖 Manifest 发布，不用于触发 projection 的自我重算。

V1 使用粗粒度用户级 epoch：一次失效可能使多个授权需要重新签发。这是有意接受的可用性代价，避免在 V1 引入复杂的按动作失效图。

新输入 MUST 经版本化的 mutation classification 分成 `INVALIDATING` 或 `NON_INVALIDATING_PENDING_PUBLICATION`。无法分类而可能影响现有授权时采用前者。原始高频样本的单纯到达不默认递增两个计数器。

### 0.4 与 v1.1 的关系

本文件替代 v1.1 中与证据准入、generation、授权、规划重试和 replay 冲突的语义，其余业务约束继续适用：每用户一个 active Program；每用户/local date 一个 active DailyPlanBundle revision；V1 每 bundle 最多一个计划训练 session；只有符合准入规则的实际已完成 A/B/C 训练推进序列；pending durable proposal 不参与日常规划。

上述唯一性与禁止条件必须在最终提交边界强制执行，不能只由前端或 Agent 遵守。Multiple-session 扩展另需定义跨 session 的执行暴露与营养耦合，不因数据结构允许多个 child 就自动获得产品授权。

## 1. 总体不变量

| ID | 不变量 |
|---|---|
| INV-01 | Prescription 中的计划值 MUST NOT 补全 actual execution。 |
| INV-02 | 模型自报 confidence、reasoning、citation 或 command text 不产生 admission/approval/authorization。 |
| INV-03 | 同一 underlying event 的多来源记录 MUST NOT 增加独立训练事件计数。 |
| INV-04 | 无法证明成功，不等于没有 physiological exposure。 |
| INV-05 | Evidence Resolver 的覆盖范围由动作政策定义，不能由 Agent 的引用列表缩窄。 |
| INV-06 | Projection 是否可复用由 dependency basis 决定，不由其 generation 数字是否最新决定。 |
| INV-07 | 只有 Manifest 的原子发布递增 decision_generation。 |
| INV-08 | 紧急失效不等待模型、projection、Manifest 或替代计划。 |
| INV-09 | Authorization 的内容绑定、epoch、scope、时间和控制状态必须共同有效。 |
| INV-10 | 失效的旧 Manifest / 旧 attempt 不能重新产生执行权限。 |
| INV-11 | 所有 attempt、repair、stale restart 和实际外部请求共享根预算。 |
| INV-12 | 外部调用结果未知不恢复已占用预算；晚到结果不恢复失去的提交权。 |
| INV-13 | 新 request revision 使旧 attempt 失权，不重置根预算。 |
| INV-14 | 替换 Fitness 内容必然使依赖其内容的 Demand 与 Nutrition 失效。 |
| INV-15 | 模型摘要始终为非命令推断；转换或重复总结不能提升 trust / authority。 |
| INV-16 | Replay 不能读取 knowledge cutoff 之后才被系统知道的个体证据及人工修正。 |
| INV-17 | LLM 等待、外部网络调用、长时间特征计算 MUST NOT 发生在协调事务内。 |
| INV-18 | 授权只决定建议可否执行，不能阻止保存用户实际上已经发生的训练事实。 |

## 2. 共同事务与时间模型

### 2.1 用户协调边界

本规范要求一个用户级逻辑协调点，不指定最终表结构。下列操作必须通过同一短事务协调机制串行化相互冲突的读写：

- 输入修订发布与失效分类；
- ProtectiveHold / revoke / control command；
- Manifest 原子发布；
- intent request revision、lease/fence 更新；
- 处方提交与授权签发；
- START / RESUME execution。

实现可以采用统一协调记录的行锁与 CAS。仅在事务外先读取版本，再执行无保护写入，不满足协议。多个锁有固定全局顺序；数据库事务冲突允许有界重试，但必须重新读取 guard，不能重放旧许可。

所有对外可见的状态变化与 outbox 事件在同一事务提交。outbox 可重复投递，消费者 MUST 幂等；数据库内的失效屏障立即生效，不依赖 outbox 已送达。

### 2.2 线性化语义

当 START 与 REVOKE 并发时，以成功提交到用户协调点的顺序为准：

- REVOKE 先提交：START MUST 失败。
- START 先提交：允许记录当时的开始；随后 REVOKE 使继续执行失权，保留开始历史。
- 服务端不能撤销已发生的物理动作；离线客户端不能获得“实时撤销已送达”的保证。

### 2.3 时间

授权和 deadline 使用服务端可信时间与 UTC instant；local_date 同时绑定 timezone / calendar policy。有效区间使用 `[valid_from, valid_until)`。自然过期不依赖后台作业更新 status。

跨午夜、时区变化和夏令时不得使同一授权被错误地用于另一个 session scope。客户端时间不是授权依据。

## 3. 协议一：Evidence Admission Protocol

### 3.1 核心对象

| 对象 | 必须保留的语义 |
|---|---|
| EvidenceRevision | 来源身份、来源修订、内容摘要、observed/effective time、系统 known time、记录时间、trust class、command authority |
| CandidateAssertion | 主体、谓词、值/单位、assertion type、否定、模态、不确定性、字段级 provenance、extractor version |
| EventAssociationDecision | 哪些 evidence 指向同一 underlying event、匹配依据、版本、歧义与撤回关系 |
| AdmissionDecision | assertion/evidence basis、action scope、结果、policy version、reason codes、supersedes、knowledge/effective interval |
| EvidenceResolution | 固定 Manifest 与动作下的支持、反证、重复、被替代项、覆盖情况及 provenance |

聊天文本必须保留原文 span；文件抽取应保留页码、坐标或稳定 span、原始抽取文本。用户报告保留 `USER_REPORTED` 性质，即使被接受用于特定动作也不升级为客观测量。

计划可作为理解语境，但不能作为实际完成量的补全来源。缺失字段保持缺失；零、未测量、不适用和解析失败必须有不同语义。

### 3.2 用途资格与不对称

V1 至少支持：

```text
DISPLAY
ACCOUNT_OBSERVED_EXPOSURE
AUTHORIZE_PROGRESSION
TRIGGER_PROTECTIVE_HOLD
ESTABLISH_RESTRICTION
CLEAR_RESTRICTION
ADVANCE_SEQUENCE
AUTHORIZE_NUTRITION_ADJUSTMENT
AUTHORIZE_DURABLE_CHANGE
```

结果为 `ELIGIBLE / NOT_ELIGIBLE / UNRESOLVED`。这是用途资格，不是全局 verified 布尔值。

资格政策 MUST 区分扩大权限与保护性收缩。存在不确定风险时可以触发临时 hold，而不形成已诊断 injury。建立、解除长期限制使用各自政策，不允许由“暂停期限到了”推导为健康事实已恢复。

`AUTHORIZE_DURABLE_CHANGE=ELIGIBLE` 只表示满足证据前提，不取代用户批准或已配置的变更类自动批准政策。

### 3.3 状态迁移

EvidenceRevision 和已写入 Assertion 内容不可原地更改。业务状态通过追加决策与 supersession 得到：

```text
EvidenceRevision
  → CandidateAssertion
  → AdmissionDecision(scope, ELIGIBLE | NOT_ELIGIBLE | UNRESOLVED)
  → newer AdmissionDecision supersedes previous decision
```

| 事件 | 允许行为 | 禁止行为 |
|---|---|---|
| 抽取含歧义 | 保存候选、定向确认、按范围限制使用 | 用模型 confidence 直接批准 progression |
| 新反证/更正 | 追加 evidence/admission 修订，失效相关使用资格 | 覆写原 admission 历史 |
| 人工解除限制 | 验证独立 command capability 与 clearance policy | 从普通聊天摘要、计划完成或未再上报推导解除 |
| 来源重复 | 关联同一事件、保留多来源证据 | 重复累加独立样本 |
| 事件匹配歧义 | 保留 ambiguous association，按政策限制计数 | 按相近时间武断合并，或默认当作多个独立成功 |

多来源不自动等于独立佐证：provider 可能转发同一上游测量。源血缘可识别时 MUST 保留；未知时不假设独立。

### 3.4 Exposure 区间

Exposure 至少包含已确认下界、可能上界、单位、统计口径、窗口、resolution status 和 basis。

上界没有依据时 MUST 为 unknown/unbounded，而不是从原处方中复制一个有限值。跨来源有重复不确定性时，禁止机械相加各个上界或下界而不说明事件关联假设。

Policy 决定未知上界下允许哪些行动。不得把 missing、unresolved 或不能计入 progression 的暴露当成零。

### 3.5 Authoritative Evidence Resolver

输入：主体、动作类型、动作参数、exercise/movement identity、Manifest ID、obligation policy version。

输出 MUST 分开：

```text
supporting_events
contradicting_events
superseded_or_retracted_items
event_association_status
coverage: COMPLETE_FOR_POLICY | PARTIAL | UNKNOWN
consistency: CONSISTENT | CONFLICTED | UNRESOLVED
query_scope_and_window
source_watermarks
truncation_status
basis_hash
```

“完整”只表示满足已定义来源和时间窗口的政策覆盖，不宣称掌握现实世界的一切事实。Conflict 与 coverage 是两个维度，不能用一个枚举混合。

Agent citations 用于解释，并可被检查是否真实支持陈述；它们 MUST NOT 缩小 resolver 查询范围。结果截断、关键来源缺失或 resolver 故障时，需证据义务的动作不得获得授权。

Resolver 必须读取固定 Manifest 的 admitted basis。它不自行读取 cutoff 之后的新事实；当前紧急风险由独立 hold / epoch 检查拦截。

### 3.6 Blueprint 与 correction

`BlueprintResolutionProposal` 是解释；`SequenceEligibilityDecision` 是用途资格。PROBABLE_A 可以与 sequence_eligible=false 共存。

序列是按有效训练发生顺序、已接受完成标准及版本化 tie-break 规则重建的投影。历史补录或更正不能按到达顺序追加一次 pointer advancement。部分训练仍可贡献已接受的 exposure。

更正必须：保存新版本 → 追加 admission/association 决策 → 标记依赖过期 → 对影响现有行动依据的更正推进 authorization_epoch → 重建投影 → 发布新 Manifest。

V1 可保守失效该用户所有尚未提交的 attempt。历史 Manifest 仍不可变，改变的是其可用于新行动的资格。

### 3.7 信任与命令

模型摘要固定为 `MODEL_DERIVED / NON_COMMAND`，并保留源证据引用。Provider free text、文件、用户引用和模型输出都不能构造 approval/clearance capability。

Durable approval V1 采用专用确认界面，服务端绑定 proposal ID、内容摘要、作用范围、基础 program/policy 和防重放身份。批准后的实际激活仍需重新检查当前政策、依赖和权限；批准不是无限期可执行通行证。

### 3.8 事务与失败

- 原始接收可独立提交，使证据不因解析失败丢失。
- 会影响现有授权的 admission 撤回/修改，其生效与 epoch 推进 MUST 同事务完成。
- 解析服务失效：保留原始证据与 unresolved；禁止伪造 canonical projection。
- 风险信号走保护路径，不得等待完整抽取成功。
- Provider 更正乱序、来源回滚或关联冲突：保留版本与冲突，不使用最后到达者自动覆盖一切。

## 4. 协议二：Decision Publication Protocol

### 4.1 三层定义

`InputRevision` 是可定位的不可变输入修订；`ProjectionBasis` 是该投影实际读取的修订集合及计算版本；`DecisionManifest` 是正式发布给 planner 的兼容输入集合。

每个 projection type MUST 声明 dependency signature，包含读取集合、窗口、缺失值语义、mapping/policy/engine 依赖，以及用于发现“新增行”的集合修订。仅列出已读行无法覆盖 absence dependency。

### 4.2 Manifest 内容

```text
manifest_id, user_scope, decision_generation
admitted_factset_revision / immutable revision references
program_revision, policy_bundle_id
projection_ids + their dependency bases
mapping / event-association revisions
captured_authorization_epoch
source coverage / watermarks
created_at, valid_until, local_date / timezone policy
content_hash
```

DecisionSnapshot 是一次 attempt 对 Manifest、mandatory context 与读取证据的绑定，不是第二个可修改的事实源。

### 4.3 发布状态机

```text
BUILDING → READY → PUBLISHED
    ├─ BUILD_FAILED
    └─ STALE
READY → STALE | REJECTED
```

失败或 stale 的 build 可以产生新 build，不能原地修改已 PUBLISHED 的 Manifest。Manifest 历史保留；“是否最新”和“是否可用于新授权”由当前协调状态与 guard 判定。

### 4.4 发布算法与事务边界

1. 短一致读取取得输入修订前沿、active program/policy、authorization_epoch。
2. 事务外构建/复用 projections，生成 dependency signatures 与 READY manifest。
3. 发布短事务进入用户协调边界，重新验证输入前沿、依赖、active program/policy、epoch 和有效期。
4. 任一需要的依据变化则判 STALE；不得只把旧内容贴上新 epoch。
5. 同事务递增 decision_generation、保存不可变 Manifest、更新 current-manifest pointer、写 outbox。

依赖不受变化影响的投影允许复用。Projection 自身完成不递增 decision_generation。重复发布相同 build 使用 idempotency key，不得重复递增。

### 4.5 两种工具读取

**默认：** 工具读取 snapshot/Manifest 所引用的不可变事实与投影。

**V1 受限扩展：** 必须查询尚未物化的历史时，可按 Manifest 中的修订与 knowledge boundary 做稳定历史查询。若只能查询 live mutable view，必须证明其相关 input frontier 与 Manifest 一致，并在同一一致读取中取得数据与版本，随后校验未改变；否则返回 STALE/UNAVAILABLE。

**仅检查 generation before == generation after 不足以放行 live 查询。** 新输入可能已经接受但尚未发布 Manifest，generation 仍不变。必须绑定输入修订，或拒绝该 live 读取。

generation 与 epoch 的检查来自权威协调存储。落后的读副本不得用来证明“没有新撤销”。

### 4.6 Mandatory context

至少包含目标优先级、Program、当前约束、restrictions/holds、overrides、sequence、progression、recent execution、数据质量与时间，以及 manifest/epoch/policy 身份。

这些块可以使用经验证的结构化摘要，不得为 token 预算静默省略。无法容纳或缺少必须证据时，返回结构化不足，不要求模型“尽力猜”。

投影标记 unavailable 可以出现在部分决策视图中，但不得伪装为完整值；哪些动作因此被禁用由 action obligations 决定。

### 4.7 失败语义

- Builder 崩溃：未发布的 view 不可见；旧授权只在自身有效性仍成立时可继续使用。
- 接受输入但投影未完成：不发布混合视图；需要失效的行动已由 epoch 先行阻断。
- Publish 与 urgent revoke 竞争：revoke 先成功则 publish 的 epoch guard 失败；publish 先成功则随后的 epoch 变化阻断基于它的新授权。
- Projection code 错误：撤回受影响发行版本，按政策推进失效屏障，重新构建；不能修改历史输出冒充当时结果。

## 5. 协议三：Authorization Protocol

### 5.1 内容、签发与状态

PrescriptionRevision 内容不可变。AuthorizationIssuance 绑定：

```text
authorization_id, user_scope
prescription_revision_id + canonical content_hash
decision_manifest_id, policy_bundle_id
authorization_epoch
evidence_resolution_ids / obligation results
execution_scope, valid_from, valid_until
issuance_reason: AI_PLAN | REUSE | FALLBACK | REVALIDATION
```

JSON/hash 的规范化规则必须版本化：单位、枚举、缺失值、字段排序和默认值不能产生不稳定依赖。安全判断不得只依赖未绑定的自由文本。

授权签发记录不可变；suspension/revocation/cancellation 是追加事件。数据库状态列可以作为投影缓存，不能成为唯一执行判据。

### 5.2 授权状态机

```text
ISSUED → SUSPENDED | REVOKED | EXPIRED
SUSPENDED → REVOKED | EXPIRED
```

同一授权不允许 SUSPENDED/REVOKED/EXPIRED → ISSUED。问题解除后签发新授权。相同处方内容可对应多个不同时期的授权；重新签发必须满足当时全部 guard。

保护性 hold 可有 review_due_at；到期表示需要处理，不默认清除。若特定政策允许自动解除，必须是显式、版本化的解除依据，并且仍需重新签发，不能恢复旧授权。

### 5.3 Authorize guard

新签发必须同时满足：

```text
attempt is current and authorized to commit
request_revision matches
fence token and unexpired lease match
root intent is live and before deadline
snapshot manifest is the current published manifest
manifest captured epoch == current authorization_epoch
manifest / evidence / policy validity holds
no applicable protective hold / stop / restriction conflict
all authoritative evidence obligations pass
single and rolling policy envelopes pass
proposal dependency hashes match
prescription content has passed semantic validation
```

新签发、处方提交、旧 bundle supersession、intent 成功终态和 outbox MUST 在一个短协调事务内原子完成。最终事务内无需重跑 LLM，但必须重检所有可变 guard；外部计算的 validation certificate 绑定上述 basis，basis 不匹配即失效。

Policy envelope 同时约束处方与已接受的实际执行暴露；不能只累计计划量或只累计实际量而重复/漏计。V1 必须明确窗口、单位、去重、未知暴露处理和实际执行替代原计划预留的规则。

### 5.4 执行资格函数

```text
is_executable(prescription, authorization, actor, now, execution_scope)
```

必须检查主体、内容 hash、scope、时间、epoch、控制事件、hold、policy admissibility、处方当前可执行关系和 execution 状态。

已有授权不要求始终引用最新 Manifest：非失效性的普通发布不强迫正在训练的用户切换计划；但相关失效输入 MUST 推进 epoch，或由显式有效性谓词捕获。新签发则必须使用最新可授权 Manifest。

### 5.5 START / CONTINUE / RESUME / COMPLETE

| 命令 | 必须行为 |
|---|---|
| START_SESSION(P,A,key) | 同事务检查执行资格，创建或幂等返回 execution，绑定确切 P/A 与开始时刻 |
| CONTINUE / foreground check | 按执行政策重新检查是否失权；不得仅依赖开始时曾有效 |
| PAUSE / stop / revoke | 记录停止资格与原因；安全事件不受 training-start lock 影响 |
| RESUME | 需要当前有效授权；必要时签发新 A，追加 resume binding，保留原 START A |
| COMPLETE / ingest actual | 保存实际事实，即使动作发生于授权失效后；不得倒填一个当时不存在的授权 |

普通重计划只能影响尚未执行部分的明确新安排，不能改写已经完成的实际组次或静默替换已开始 session 的处方。

### 5.6 紧急控制通道

有授权的 STOP / FORCE_REST，以及符合 protective policy 的风险信号，在短事务内：

```text
persist control / hold
increment authorization_epoch
append revocation/invalidation record
invalidate commit authority of old attempts
append outbox
COMMIT
```

该事务不调用模型，不等待 projection，不受普通规划预算或 revision cooldown 限制。可单独限制滥用流量，但不得复用普通规划队列导致停止请求饥饿。

“自由文本风险可即时识别”不是确定性保证。V1 必须提供明确的停止/不适入口。对进入风险上报通道的未解析文本，可先施加适用的 pending hold，再解析；任意普通聊天的风险识别只能按经评测的检测能力声明，不能声称零漏检。风险解析不可用时的权限收缩必须写入 rollout policy。

### 5.7 降级与 UI

PreauthorizedFallback 表示已审核的模板与适用谓词，不表示不经当前检查即可执行。实际使用时仍需匹配当前 basis、hold、scope、有效期与政策，并签发当次授权。

必须区分：`AI_GENERATED_CURRENT / REUSED_VALID_PLAN / PREAUTHORIZED_FALLBACK / UNAVAILABLE`。显示最后决策时间、数据缺失与可执行范围；系统不可用不得包装为个性化健康判断。

复用旧内容可以通过当前资格检查继续使用仍有效的 A，或签发新 A；禁止直接延长旧授权的 valid_until。

客户端只可渲染已提交处方为可执行。流式草案与 planning progress 不具有授权。离线模式仅允许政策规定的有限期凭据，明确无法保证撤销实时到达；不符合离线条件时不得离线启动。

## 6. 协议四：Persistent Bounded Planning Workflow

### 6.1 对象与独立版本

PlanningIntent 包含稳定根 ID、主体、local date/purpose、request revision、constraints fingerprint、deadline、根预算、状态。

PlanningAttempt 绑定 intent、request revision、Manifest、captured epoch、fence token、模型/提示/工具/策略版本和 proposal dependencies。

Concurrency partition 与语义去重键分离。Fingerprint 是服务端规范化约束的摘要，不能仅根据自然语言表面相同判定意图相同。

### 6.2 Intent 状态机

```text
ADMITTED → RUNNING → FOUND_VALID_PLAN
    │          ├─ PROVEN_CONSTRAINT_CONFLICT
    │          ├─ SEARCH_BUDGET_EXHAUSTED
    │          ├─ MODEL_REFUSAL
    │          ├─ MODEL_OUTPUT_INVALID
    │          ├─ DEPENDENCY_UNAVAILABLE
    │          ├─ STALE_RETRY_EXHAUSTED
    │          ├─ DEADLINE_EXCEEDED
    │          └─ CANCELLED
    └─ DEADLINE_EXCEEDED | CANCELLED
```

终态不可重新打开。单次 attempt 的错误可以按预算内政策修复，不必立即成为 intent 同名终态。成功只能与真实处方/授权提交同时发生；模型产生合法 JSON 不等于成功。

`PROVEN_CONSTRAINT_CONFLICT` 必须附形式化约束与输入 basis 下的冲突证明或确定性检测证据；结论只覆盖该形式化问题。模型多次未成功只能归为搜索/输出失败，不能推导现实目标不可满足。

### 6.3 Attempt 状态机

```text
CREATED → LEASED → BUILDING_CONTEXT → FITNESS
   → DEMAND_FEATURES → NUTRITION → VALIDATING → COMMIT_READY → COMMITTED
```

任一未提交状态可转 `STALE / FAILED / CANCELLED / LEASE_LOST`。上述终态 attempt 不得直接继续提交；重试产生新 attempt，消耗同一根预算。

修复发生在工作流明确的 transition 上，每次消耗相应预算。不得让 Agent 任意构造回到起点的控制指令。

### 6.4 Single-flight 与 request revision

| 新请求 | 处理 |
|---|---|
| 相同 scope、fingerprint、当前 basis | join 当前 intent/attempt |
| 同一目标的时间/器械等变化 | 同事务递增 request_revision，旧 attempt 失权，保留预算和 deadline |
| STOP / FORCE_REST / risk | 进入独立控制路径；不得等待旧模型 |
| 已终态后明确重新请求 | 经用户级准入后创建新 intent |
| 不同 session purpose | 按执行和冲突政策判断是否可并发；不得仅因 key 不同绕过同日限制 |

约束更新不默认延长 deadline。自动事件是否能创建新 intent 必须由版本化 admission policy 决定，防止自触发循环。新 root 受用户小时/日配额、模型容量与系统准入约束。

### 6.5 Lease 与 fencing

领取或接管 intent 原子产生更大的 fencing token 与 lease expiry；heartbeat 只能由当前 owner/token 延长，不能超过 intent deadline。

所有共享工作流写入及提交检查 token、lease、request revision 与 intent 状态。旧 worker 不因仍持有进程或网络连接而拥有写入权。

独立 Watchdog/Reaper 扫描过期 lease/deadline、封闭旧提交权、标记未确定外部调用、在允许时安排接管。恢复任务、取消和 admission 使用独立容量，不能被普通推理队列耗尽。

网络请求不能被数据库 fencing 从物理上撤回。一个已经获准 dispatch 的旧进程可能稍后才真正发出请求；其预留预算必须覆盖这次可能调用，但其结果不能恢复业务提交权。

### 6.6 Reservation ledger 与不可判定发送窗口

每次可能到达 provider 的物理请求必须有唯一 call reservation。推荐状态：

```text
RESERVED
  ├─ CANCELLED_BEFORE_DISPATCH
  └─ DISPATCH_INTENT
       ├─ DISPATCHED
       ├─ SETTLED
       └─ OUTCOME_UNKNOWN
DISPATCHED → SETTLED | OUTCOME_UNKNOWN
OUTCOME_UNKNOWN → SETTLED  (仅可靠对账)
```

`DISPATCH_INTENT` 在网络调用前持久化，语义为“此请求从现在起可能已发出”。这是故障判定边界；`DISPATCHED` 仅是后续诊断信息，不能承担“唯一可能计费”的边界。

执行顺序：

1. 预留短事务：校验 intent/lease/request revision、截止时间与根预算，原子占用 call slot、token/cost 上界。
2. 发送许可短事务：重新校验 owner/fence/deadline，将 reservation 转 DISPATCH_INTENT。
3. 事务外发送一次请求。SDK 隐式重试必须禁用，或每次实际重试都在同一受控账本内预留；不能把一次 SDK 调用当成一次物理请求。
4. 收到结果后幂等结算 actual usage；应用结果前再次检查业务写入资格。

若第 3 步之后、第 4 步之前崩溃，即使从未写过 DISPATCHED，恢复者仍必须按可能已消耗处理。新 worker 不得用同一 reservation 再发一次；必须新预留，或使用已验证具有所需幂等语义的 provider 协议。

仅 RESERVED 且通过原子状态竞争确定不存在发送许可时，允许取消并释放。DISPATCH_INTENT 之后缺少响应、网络超时或取消请求都不构成“未消耗”的证明。

### 6.7 三类预算

| 类别 | 含义 |
|---|---|
| Enforceable limits | 本服务可限制的请求次数、工具次数、输入规模、provider 支持的输出上限、启动/提交截止时间 |
| Reserved usage | 已预留的最大可计入消耗，包含 pending 与 outcome unknown |
| Settled actual usage | 可靠 provider 回执/对账确认的消耗 |

预算检查使用 settled + 所有未结算预留 + 本次预留，不允许并发透支。上界必须覆盖实际配置下所有计费维度；无法界定时不能宣传严格货币上限，应拒绝该配置或明确采用仅次数/token 的强限制。

未知结果可按预留值计入 intent 的预算占用，但不能在财务报表中伪称 provider 已确认收取该金额。截止时间约束本地继续工作和提交权，不保证远端推理与计费已停止。

晚到响应允许通过专门的幂等结算入口补齐账本和不可变证据，不允许旧 worker 任意修改 intent、request revision 或授权。

### 6.8 跨 Agent 依赖

```text
FitnessProposal hash F
  → PrescriptionDemandFeatures hash D (basis F + method versions)
    → NutritionProposal hash N (basis F,D,Manifest,policy)
```

Fitness 任何授权相关内容变化都使旧 D/N 不适用于新 bundle。修复后必须生成新 D，并重新运行或按显式可验证规则重新计算 N；不能只改 N 的引用 hash。所有额外请求继续消耗根预算。

Demand 字段明确区分 `PRESCRIBED_QUANTITY / TARGET / ESTIMATE`，不作为实际执行或生理事实。Cross-domain checker 使用可计算特征、证据与 Policy Envelope；不得只依赖 Agent 自评的 MODERATE 等标签。

### 6.9 失败与终态竞争

- SDK/模型 transient error：在根预算与 deadline 内重试；不可重试错误直接结束相应路径。
- Refusal：独立分类，不用格式修复 prompt 强行重试。
- malformed/incomplete：不得激活局部结果；修复需预算和明确政策。
- COMMIT 响应丢失：按 intent/commit id 查询事实，不能重新无条件签发授权。
- CANCEL、deadline 与 COMMIT 竞争：由协调事务顺序决定；watchdog 不得把已成功提交的 intent 改回失败。
- Provider outage：熔断、并发上限与重试配额控制共享容量；fallback 仍走 Authorization Protocol。
- 正常队列饱和：可以拒绝新的规划，不得使停止/撤销通道不可用。

## 7. 协议五：Replay Protocol

### 7.1 两种模式

| 模式 | 问题 | 规则 |
|---|---|---|
| Historical Reconstruction | 当时系统依据什么做了什么 | 使用当时可知的证据、当时政策/算法/映射；优先重放已保存输入输出与验证记录 |
| Current Policy Backtest | 当前版本面对当时可知证据会如何决定 | 固定过去 knowledge cutoff，使用明确指定的当前政策/算法版本，重新计算候选与投影 |

Historical Reconstruction 不承诺重新调用同名模型得到逐字相同输出。历史响应和工具证据是复原决策链的主要依据；旧模型不可用或随机性导致不同必须标注，不伪称精确复现。

### 7.2 时间边界

每类实体逐一定义 effective time、系统首次持久获知的 known time、recorded time、supersession 的生效及获知时间。known_at 由可信接收流程分配，不能接受 provider 传入的时间来回填系统知情历史。

迟到证据可以具有早的 effective_at 和晚的 known_at；过去 cutoff 查询必须仍排除它。政策下的历史更正、event merge/split、admission 撤回及 mapping 变更都遵守同样边界。

Replay 的所有上下文工具、检索索引、projection、resolver 和 cache key 都绑定 replay mode、cutoff、release bundle 与主体。不得从 live current tables 偷取结果。

### 7.3 当前算法与未来知识

Current Backtest 允许使用当前通用算法，但不能携带 cutoff 之后才人工得知的个体映射、偏好、限制解除或结果标签。用当前逻辑对当时原始证据重新推导的结果，必须标记为 counterfactual derivation，不冒充当时已知事实。

用未来 evaluation outcomes 调参后再在相同历史上报告提升，不构成独立验证。Release evaluation 必须声明训练/调参/测试切分、冻结时间、可用数据与泄漏检查。当前模型的广泛训练知识无法被简单还原为过去模型知识，报告必须说明这一反事实评估限制。

### 7.4 Replay 状态机

```text
DEFINED → INPUTS_RESOLVED → RUNNING → COMPLETED
                ├─ BLOCKED_MISSING_ARTIFACT
                ├─ INVALID_KNOWLEDGE_BOUNDARY
                └─ FAILED
```

Replay 环境不能签发 production authorization、写用户 live state 或触发通知。输出写入隔离 evaluation scope；模拟授权显式标记为 simulation。

### 7.5 Outcome separation

必须分别记录 prescription、actual execution、adherence estimate 与 outcome，保留各自证据和不确定性。未上报不是零执行或正常恢复。

新方案的反事实输出不能直接与旧方案下真实 outcome 配对并宣称因果效果。历史回放可评估一致性、授权违规、判断差异和参考评价；疗效/训练效果结论需要另行定义的研究或实验设计。

Weekly Analyst 可以提出关联性解释与 durable proposal；进入自动 durable change 前，必须完成 intervention/outcome 定义、结果窗口、release gate、监控及回滚协议。

### 7.6 最小 Replay 输出

```text
replay_mode, cutoff, release_bundle, input_manifest/hash
included / excluded evidence and reasons
admission / mapping / projection versions
recorded-output replay or fresh-model-run marker
proposal + validation + simulated authorization results
missing artifacts / stochastic limitations / leakage audit
```

## 8. 端到端事务清单

| 事务 | 原子写入与 guard | 事务外工作 |
|---|---|---|
| T1 Evidence receive | 来源幂等、raw revision、可信 known_at | 解析、关联候选 |
| T2 Admission/control update | admission/hold 修订、必要的 epoch 推进、失效事件、outbox | 投影计算、通知投递 |
| T3 Manifest publish | 依赖前沿/epoch 校验、generation 递增、manifest/current pointer、outbox | 构建与复用 projections |
| T4 Intent admit/update | single-flight、request revision、配额、旧 attempt 失权 | 上下文与推理 |
| T5 Lease/reservation | lease/fence、预算预留、dispatch permission 各自原子迁移 | 网络请求 |
| T6 Commit/issue | 全部 guard、处方、授权、bundle supersession、intent success、outbox | 模型、证据检索、计算验证 |
| T7 Start/resume | 当前执行资格、execution binding、幂等、outbox | 用户物理执行 |
| T8 Settle/reap | 幂等结算或旧 owner 失权、unknown/terminal 状态 | provider reconciliation、重新调度 |

T2/T3/T4/T5/T6/T7/T8 对相同用户/intent 的竞争 MUST 遵循统一锁序和 guard。流水线各阶段独立事务不是跨阶段原子保证；必须由不可变 basis、版本与最终 guard 连接。

## 9. 自动激活验收矩阵

这些是待实现的验收规范，不表示当前已执行通过。每项应包含 Given/When/Then、故障注入位置和持久状态断言；关键并发项应覆盖不同事务提交顺序。

| ID | 反例/故障 | 必须断言 |
|---|---|---|
| E01 PLAN_NEVER_COMPLETES_ACTUAL | 计划三组，用户仅完成一组 | 不产生另外两组 actual；不虚增 progression |
| E02 UNRESOLVED_RISK_DOES_NOT_DISAPPEAR | 风险通道文本尚未完整解析 | 按政策建立 pending hold；相关行动不能因 unresolved 放行 |
| E03 DUPLICATE_SOURCES_DO_NOT_MULTIPLY_EVENTS | 同一训练来自 chat/Hevy/watch | 独立事件数为一，来源仍保留 |
| E04 AMBIGUOUS_EVENT_MATCH_IS_NOT_TRUTH | 两次接近的训练可能重复 | 不强制合并或认定独立成功；保留关联不确定性 |
| E05 UNKNOWN_EXPOSURE_IS_NOT_ZERO | 完成量不完整 | 下界保留，上界无依据时 unknown；不生成虚假零 |
| E06 CONTRADICTION_CANNOT_BE_CHERRY_PICKED | 引用早期成功、忽略后来失败 | Resolver 返回反证，义务按完整政策集合判断 |
| E07 CORRECTION_WITHDRAWS_ACTION_BASIS | 更正曾授权 progression 的记录 | admission/projection/新授权资格失效；历史仍可重建 |
| E08 SUMMARY_CANNOT_GRANT_AUTHORITY | 外部备注经多轮总结成偏好/批准 | summary 不获得命令或批准资格 |
| D01 PROJECTION_DOES_NOT_BUMP_GENERATION | readiness 计算完成 | generation 不变，直到 Manifest 原子发布 |
| D02 REUSE_USES_BASIS_NOT_AGE | 无关输入变化 | 合法复用未受影响 projection，无假 stale 循环 |
| D03 UNPUBLISHED_INPUT_CANNOT_LEAK | generation 不变但新输入已接受 | live tool 不能混入未绑定修订 |
| D04 ABSENCE_DEPENDENCY_IS_TRACKED | 新插入 restriction/事件 | 集合修订或 epoch 捕捉变化 |
| D05 PUBLISH_CANNOT_OVERWRITE_URGENT_EPOCH | 构建期间 hold 生效 | 旧 build 发布失败或不能授权；不得贴新 epoch 强行发布 |
| A01 REVOKE_PRECEDES_REPLAN | revoke 后模型不可用 | 旧授权仍立即失效，不等待替代计划 |
| A02 STALE_MANIFEST_CANNOT_REAUTHORIZE | epoch 更新而 generation 未更新 | 旧 Manifest 不能签发新 A |
| A03 START_REVOKE_SERIALIZES | START 与 REVOKE 并发 | 按提交顺序决定；不得出现 revoke 后成功开始 |
| A04 EXPIRY_NEEDS_NO_STATUS_JOB | 超过 valid_until，缓存 VALID | evaluator 返回不可执行 |
| A05 REAUTH_DOES_NOT_REWRITE_HISTORY | P7 重新签发 A2 | A1 不恢复，原 START 仍绑定 A1 |
| A06 FALLBACK_IS_NOT_PRIVILEGED | hold 生效且 AI 故障 | fallback 同样受限，无适用项则 UNAVAILABLE |
| A07 STOP_PATH_SURVIVES_QUEUE_SATURATION | 推理队列/预算耗尽 | 停止与撤销仍可处理 |
| A08 ACTUALS_SURVIVE_UNAUTHORIZED_EXECUTION | 用户失权后仍实际训练 | 保存 actual 和当时授权状态，不伪造授权或丢记录 |
| W01 CRASH_DOES_NOT_REFUND_EXTERNAL_BUDGET | DISPATCH_INTENT 后任意位置崩溃 | 预留保留；即使无 DISPATCHED 也不可退款 |
| W02 RESERVE_CANCEL_RACE_IS_ATOMIC | 取消与发送许可竞争 | 不能同时释放预算并获得发送许可 |
| W03 SDK_RETRIES_ARE_ACCOUNTED | provider transient error | 每次物理请求被预算覆盖，无隐式免费重试 |
| W04 SINGLE_FLIGHT_PRESERVES_NEW_CONSTRAINTS | 70min/full gym → 20min/no equipment | request revision 增长，旧 attempt 无提交权，预算不重置 |
| W05 OLD_WORKER_CANNOT_COMMIT | token 7 过期，token 8 接管 | token 7 仅可经专门入口结算，不可提交处方 |
| W06 LATE_RESULT_CANNOT_REOPEN_INTENT | 已取消/过 deadline 才返回 | 结果可审计，intent 不复活 |
| W07 FITNESS_CHANGE_INVALIDATES_NUTRITION | F1/D1/N1 → F2 | D1/N1 不得直接用于 F2；重新计算消耗原预算 |
| W08 COMMIT_ACK_LOSS_IS_IDEMPOTENT | DB 已提交，响应丢失 | 查询返回原结果，不重复签发或重复 supersede |
| W09 SEARCH_FAILURE_IS_NOT_INFEASIBILITY | 多次模型失败 | 不产生 PROVEN_CONSTRAINT_CONFLICT |
| R01 FUTURE_CORRECTION_IS_EXCLUDED | 九月更正八月记录 | 八月 cutoff 不读取九月知识 |
| R02 REPLAY_MODES_ARE_SEPARATE | 同一 cutoff 两种 replay | 分别绑定历史和当前 release，不混用 |
| R03 FUTURE_PERSONAL_MAPPING_IS_EXCLUDED | 后来人工完成个体映射 | backtest 不直接导入该未来知识 |
| R04 REPLAY_CANNOT_WRITE_LIVE | 模拟得到有效计划 | 无 production authorization 或 live mutation |

## 10. 冻结前必须填写的政策配置

以下不要求在本协议里拍定训练/营养数值，但自动激活环境 MUST 有显式、版本化的值与责任人。缺少配置时禁止对应动作，不允许模型补齐。

| 配置包 | 必须确定的内容 | 缺失时行为 |
|---|---|---|
| Admission / exposure | 各用途门槛、模糊事件关联、未知暴露、反证优先规则 | 保留 unresolved，阻止需该证据的扩大权限 |
| Safety/control | protective trigger、作用范围、解除条件、风险解析故障策略 | 不开放依赖未定义保护协议的自动行动 |
| Publication | 各 projection dependency signature、输入失效分类、Manifest freshness | 不发布可授权 view |
| Policy envelope | 单次/累计/变化速率、实际与计划暴露对账、nutrition coupling | 不允许相关自动处方 |
| Authorization | scope、TTL、START/CONTINUE 检查频率、离线许可、重新签发政策 | 不签发相应执行资格 |
| Workflow | 根预算、deadline、lease、重试/修复规则、用户准入与容量 | 不启动无界 planning |
| Fallback | 模板、适用/禁止谓词、证据与有效期 | UNAVAILABLE |
| Replay/release | 历史制品保留、切分、泄漏审计、release 指标/阈值、回滚条件 | 不宣称评测通过或开放自动 durable change |

## 11. 冻结检查与实施顺序

协议进入 FROZEN 至少需要：

1. 为五个协议指定唯一写入入口、所有者、错误码与 idempotency 语义。
2. 审查所有状态迁移均有前置 guard、事务边界和失败终态；本文新增的 epoch 与 dispatch-intent 语义得到确认。
3. 对发布/revoke、START/revoke、cancel/dispatch、lease takeover/commit 等关键交错完成可执行协议测试或状态模型验证。
4. 完成最小政策配置包；未确定项有明确禁用行为。
5. 明确所有尚未确定的产品数值属于配置、受禁用条件保护，不再遗留会改变事务边界或权限含义的未决协议问题。

协议冻结之后，再推导 DDL、Pydantic/API 契约和 worker 接口；实现验收必须证明它们没有减弱已冻结不变量。DDL 完成不是协议冻结的前置条件。

可以立即实施 evidence 接收、不可变版本模型、原始训练记录、exercise catalog、Program import、outbox、本地测试环境。不得将“可开始实施”解释为“可自动激活”。

自动激活前必须通过第 9 节相关测试、端到端故障演练、授权审计与降级 UX 验证。自动 durable change 还需完成 intervention/outcome 与 release evaluation 的额外门槛。

本候选不锁定表数量、不引入通用 DAG 平台、不要求微服务；所有保证均可先在模块化单体、PostgreSQL、planner worker 与独立 reaper 中实现。
