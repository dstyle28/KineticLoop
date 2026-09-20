# KineticLoop — DB Schema Design v0.2

状态：**Logical Schema Review Candidate；不含 SQL；不代表协议已冻结。**

Canonical architecture baseline：`KineticLoop_v1.2_Protocol_Freeze_Candidate_r2.md`。本文件是其下游设计，不能以表结构覆盖协议。v1.1 中相冲突的 Evidence / generation / planning / authorization / replay 语义不再适用。

范围：从 INV-01–18 与 T1–T8 反推逻辑关系、身份与版本、约束、查询索引、唯一 command/write entrypoint、事务与锁；为 34 项验收规格建立实现落点。不引入新的架构层，不实现 DDL、ORM、数据库迁移或生产服务。

## 1. 数据建模纪律

### 1.1 三类数据，不混用权威

- **I：immutable history**。证据修订、admission、Manifest、处方、授权签发、授权事件等只追加，禁止普通运行角色更新/删除其语义内容。
- **M：mutable operational state**。当前指针、lease、fence、request revision、预算余额、投递状态等允许在唯一命令入口及 guard 内更新；变更同时写审计事件。
- **B：build/job state**。可变运行元数据与不可变完成结果分离；不能因为 build status 为 READY 就具有行动授权。

“Immutable”不取代隐私删除政策。敏感 payload 可以存储为受控 blob reference；依法或按产品政策删除后留下允许保留的 tombstone / artifact-unavailable 语义，不伪称还能完整 replay。这里不规定无限保留期。

### 1.2 共同字段与引用约束

所有用户数据使用 `subject_id`（经认证的用户/租户作用域），不接受模型指定主体。每个引用都必须证明相同主体；推荐以 `(subject_id, entity_id)` 为复合候选键并建立相应复合外键。全局只读 catalog / policy 使用独立 namespace，不能以 `subject_id=NULL` 作为任意跨用户读取的豁免。

I 类行共同包含 `id, subject_id, recorded_at, content_schema_version`，内容对象另带 `content_hash, hash_scheme_version`。有历史获知含义的对象另带 `known_at`；有现实发生时间的对象另带 `effective_at` 或有效区间。各表以下只列额外关键字段，类型暂以 ID / Integer / Instant / Decimal / Enum / TypedPayload / BlobRef 表示。

历史修订引用稳定实体 ID 与明确 revision ID。`supersedes_id` 是追加关系，不能更新旧行来擦除其历史；当前生效区间由追加决策推导。发生时间冲突有明确的 source revision / server ordering tie-break，不能使用 UUID 大小猜测先后。

用于幂等/唯一性的 logical_member_key、scope、slot 必须有明确且非空的规范值；不适用使用类型化的 NONE 语义，不能依赖 NULL 的默认唯一性行为防重。known_at 表示可信持久接收边界；只读一个事务开始时间不足以证明该时刻数据已经提交可见。历史决策优先按已保存的 Manifest/证据选择重建，任意时间 cutoff 则必须绑定可靠的持久接收记录或已提交知识前沿。

### 1.3 保证的三种强制位置

| 标记 | 含义 | 例子 |
|---|---|---|
| DB | 后续可落成唯一性、外键、非空、行内检查及写权限限制 | 同用户一天一个 head；同一 issuance ID 不可重写 |
| TX | 持锁短事务内读取、判断和原子更新 | 当前 epoch/fence；根预算不并发透支 |
| DOMAIN | 版本化领域代码或 resolver 的判断，结果绑定 basis 后由 TX 复核 | 证据是否充分；累计暴露是否符合政策 |

不得把跨行安全判断写成一个调用外部表的普通 CHECK 来假装持续有效。PostgreSQL 的 CHECK 不为其他行的未来变化提供这种保证；复合外键与唯一性适合表达身份和关系约束。[PostgreSQL Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)

索引是查询或唯一性工具，不是完整授权协议。基于 `now()` 的“尚未过期”不能成为授权唯一性的动态 partial-index 条件；过期必须运行时检查。Partial unique index 仅用于行内稳定状态谓词，例如 ADMITTED/RUNNING。[PostgreSQL Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html)

### 1.4 控制计数与输入修订

S01 仅存两个协议计数器：`decision_generation`、`authorization_epoch`。`current_factset_id` 和 `input_frontier_hash` 是不可变输入修订集合的指针/摘要，不是第三个授权 epoch。`execution_basis_event_id` 指向最近一次改变计划/执行暴露的已提交事件，是累计 envelope 校验的输入依据，不是新的授权机制。

Projection 完成不改 generation。Manifest 发布不自动改 epoch。Admission/输入发生变化时先分类：需要失效则同事务推进 epoch；无关的原始样本不进入该锁热点。

## 2. 逻辑表目录

以下 51 个关系是候选逻辑表，不是对物理分区数量、索引数量或 ORM 类数量的冻结。关系中的 payload 必须有闭合的类型契约；关键身份、用途、时间、权限与 join key 不能藏在自由文本中。

### S01 `user_decision_state` — M

- **作用/字段：** `subject_id` 主键；current_factset_id、input_frontier_hash、active_program_id、active_policy_bundle_id、current_manifest_id、decision_generation、authorization_epoch、last_control_event_id、execution_basis_event_id。
- **约束：** DB：每主体一行、计数非负、指针同主体。TX：generation 仅 T3 成功发布时递增；epoch 只由失效命令推进；指针与事件同事务。
- **索引：** 主键是用户协调锁入口；与独立 registry 共享/排他 gate 分开，不串行化不同用户的普通写入。
- **唯一写入所有者：** DecisionStateCoordinator；决策发布/输入/控制字段经 T2/T3 更新；改变计划或执行暴露的 T2/T6/T7 同事务更新 execution_basis_event_id；其余事务仅锁住并读取 guard。
- **映射：** INV-07, INV-08, INV-09, INV-10, INV-17；T2, T3, T4, T5, T6, T7, T8。

### S02 `command_receipts` — M

- **作用/字段：** command_kind、client_key、actor_scope、request_hash、status、result_entity_refs、error_code、accepted_at、completed_at。
- **约束：** DB：主体/actor_scope/command_kind/client_key 唯一。TX：同 key 同 hash 返回既有结果；不同 hash 拒绝。数据库 mutation 的 receipt 与结果同事务，不能先写 SUCCESS 再操作。
- **索引：** 幂等唯一键；completed_at 支持保留策略。不因删除旧 receipt 允许危险命令重放，见 §3。
- **唯一写入所有者：** CommandGateway 与对应原子事务；模型无权写。
- **映射：** INV-02, INV-08, INV-11, INV-13, INV-18；T1, T2, T3, T4, T5, T6, T7, T8。

### S03 `domain_events` — I

- **作用/字段：** aggregate_type/id、aggregate_revision、event_type、causation_command_id、correlation_intent_id、typed payload、effective/known time。
- **约束：** DB：聚合内 revision 唯一、引用同主体。TX：与可见状态变化同事务；不要求所有原始 telemetry 使用同一个用户序号。
- **索引：** subject/aggregate/revision；subject/known_at；correlation_intent_id。
- **唯一写入所有者：** 每个领域 command 的事务；EventWriter 负责格式，不绕过领域入口。
- **映射：** INV-07, INV-08, INV-12, INV-13, INV-16, INV-18；T1, T2, T3, T4, T5, T6, T7, T8。

### S04 `outbox_deliveries` — M

- **作用/字段：** domain_event_id、destination、delivery_status、next_attempt_at、delivery_lease、attempt_count、last_error。
- **约束：** DB：event/destination 唯一。TX：与对应 event 同事务创建；投递成功不是业务提交的前提。
- **索引：** 待投递状态/next_attempt_at、lease expiry。claim 使用队列专属锁，不反向取得 S01。
- **唯一写入所有者：** 原命令创建、OutboxDispatcher 更新投递元数据；不修改事件内容。
- **映射：** INV-08, INV-12, INV-17；T1, T2, T3, T4, T5, T6, T7, T8。

### S05 `policy_bundles` — I

- **作用/字段：** policy_namespace/version、admission/obligation/envelope/authorization/fallback/workflow 配置、dependency signatures、engine artifact refs、配置完整性报告、review provenance。
- **约束：** DB：namespace/version 唯一、不可变。DOMAIN：各模块闭合 schema、引用版本可解析。未配置与显式禁用不同；hash 不是人工审核通过的证明。
- **索引：** namespace/version；content_hash 仅做同 namespace 内容定位。
- **唯一写入所有者：** PolicyRegistry.PublishBundle；生效只经 T2 激活到用户指针，不能修改全局 alias 静默改变执行规则。
- **映射：** INV-02, INV-05, INV-06, INV-09, INV-15, INV-16；T2, T3, T6, T7。

### S06 `program_versions` — I

- **作用/字段：** program_id、revision、parent_version_id、goals、结构化 blueprint/schedule/targets、nutrition policy refs、activation basis。
- **约束：** DB：主体/program/revision 唯一。TX：唯一 active 权威是 S01.active_program_id；pending proposal 不能改变该指针。不再维护第二个独立可写 ACTIVE 标记。
- **索引：** subject/program/revision；subject/known_at。
- **唯一写入所有者：** ProgramService.ActivateApprovedProgram，或明确授权的初始 Program import；激活 T2 重检批准与 basis。
- **映射：** INV-02, INV-07, INV-09, INV-16；T2, T3, T6。

### S07 `durable_change_proposals` — I

- **作用/字段：** proposal_family_id、revision、change_class、base_program_id、base_manifest_id、exact proposed change、origin proposal/artifact、content_hash。
- **约束：** DB：family/revision 唯一、基础版本同主体。DOMAIN：变化类别与 payload 相符。改变内容必须新 revision，不修改已被批准对象。
- **索引：** subject/change_class/known_at；base_program_id。
- **唯一写入所有者：** ProgramReviewService.SubmitChangeProposal；此入口不能激活 Program。
- **映射：** INV-02, INV-09, INV-15, INV-16；T2。

### S08 `approval_issuances` — I

- **作用/字段：** proposal_revision_id、bound_content_hash、actor_id、command_receipt_id、approved_scope、base_program/policy、approval time/expiry、approval_mode。
- **约束：** DB：一次批准 command 只产生一个 issuance；subject/proposal/hash 绑定。TX：用户批准入口或明确的 change-class 自动批准政策才能写；激活时再检查有效期、基础版本与当前权限。
- **索引：** proposal_revision_id；subject/actor/time。使用同 issuance 重放 Program activation 必须返回原 activation，而非再次创建新版本。
- **唯一写入所有者：** ApprovalService.ApproveChange；撤回通过追加 domain event，不篡改 issuance。
- **映射：** INV-02, INV-09, INV-15, INV-16；T2。

### S09 `evidence_revisions` — I

- **作用/字段：** source_connection_id、source_object_type/id、source_revision/observation_key、payload hash/blob、observed_at、known_at、trust_class、source_class、command_authority=NONE。
- **约束：** DB：可靠 provider revision 时来源对象/revision 唯一；无可靠 revision 时用稳定接收 observation key 去重。payload hash 相同只可去重存储，不能删除独立时间点的测量或回滚后的新观察。
- **索引：** subject/source/object/revision；subject/known_at；subject/observed_at。
- **唯一写入所有者：** EvidenceService.ReceiveEvidence；known_at 由可信持久接收边界产生，不能回填 provider 时间。
- **映射：** INV-01, INV-02, INV-03, INV-15, INV-16, INV-18；T1。

### S10 `candidate_assertions` — I

- **作用/字段：** assertion_family/revision、evidence_revision_id、predicate、typed value/unit、negation/modality、assertion_type、field provenance、extractor artifact、uncertainty。
- **约束：** DB：证据引用同主体；结构 schema 闭合。DOMAIN：否定、未知、零不能混合；模型 confidence 仅诊断。候选无 admission/command 写权。
- **索引：** evidence_revision_id；subject/predicate/effective_at；assertion_family/revision。
- **唯一写入所有者：** ExtractionService.RecordCandidate；失败候选留痕，不自动进入事实投影。
- **映射：** INV-01, INV-02, INV-04, INV-15, INV-16；T1, T2。

### S11 `underlying_events` — I

- **作用/字段：** event_id、subject、event_kind、creation provenance、初始已知时间；表示稳定的现实事件身份。
- **约束：** DB：event_id 同主体唯一。DOMAIN：创建 ID 不等于确认事件发生，不等于获得 progression credit。事件合并/拆分由新 association decision 表达。
- **索引：** subject/event_kind/known_at。
- **唯一写入所有者：** EvidenceAssociationService；禁止由 Agent 自造 ID 后直接计数。
- **映射：** INV-03, INV-04, INV-16, INV-18；T2。

### S12 `event_association_decisions` — I

- **作用/字段：** association_family/revision、evidence_revision_id、candidate_event_ids、accepted_event_id（可空）、MATCHED/AMBIGUOUS/RETRACTED、method/policy、supersedes、source lineage。
- **约束：** DB：family/revision 唯一；单项决定的 accepted_event 只能有一个。TX：同一关联前序不能产生两个同时生效的 successor；merge/split 的关联批次原子进入新的 factset。
- **索引：** evidence_revision_id/known_at；accepted_event_id；supersedes_id。
- **唯一写入所有者：** EvidenceAssociationService.DecideAssociation；AI matching 仅提供候选。
- **映射：** INV-03, INV-04, INV-05, INV-16；T2。

### S13 `admission_decisions` — I

- **作用/字段：** assertion_id、action_scope、decision=ELIGIBLE/NOT_ELIGIBLE/UNRESOLVED、policy_bundle_id、evidence basis、reason_codes、supersedes_id、effective/known times。
- **约束：** DB：assertion/scope/decision revision 唯一；scope 非空。TX：同 scope 的当前决策更替经同一协调点，禁止并发分叉；撤回追加新决策。不允许 verified boolean 代替用途资格。
- **索引：** subject/assertion/action_scope/known_at；supersedes_id；policy_bundle_id。
- **唯一写入所有者：** AdmissionService.DecideAdmission；触发失效的决策与 epoch 变化同 T2。
- **映射：** INV-01, INV-02, INV-04, INV-05, INV-08, INV-16；T2。

### S14 `canonical_fact_revisions` — I，领域事实版本根

- **作用/字段：** stable_fact_id、revision、fact_kind、underlying_event_id、source assertion/admission refs、effective/known time、typed fact payload、supersedes_id。
- **领域形状：** WORKOUT_ACTUAL（稳定 set/bout 子身份、实际动作/数值/缺失状态）、HEALTH_OBSERVATION、NUTRITION_INTAKE、BODY_MEASUREMENT、OUTCOME_OBSERVATION。每种形状独立领域 schema；计划处方不属于此 union。
- **约束：** DB：stable_fact/revision 唯一、kind/identity/单位形状一致、actual 字段不可引用处方作为完成证据。DOMAIN：字段 provenance 与各用途 admission 对齐。被接受的用户报告仍保留 USER_REPORTED 性质。
- **索引：** subject/kind/effective_at；subject/stable_fact/revision；underlying_event_id；known_at。
- **唯一写入所有者：** CanonicalFactService.AcceptFactRevision，嵌入 T2 admission/修订事务。
- **映射：** INV-01, INV-03, INV-04, INV-16, INV-18；T2。
- **物理化边界：** 这是一个逻辑版本根，不是任意 key/value EAV。DDL 阶段可为高频 strength_sets、cardio_bouts、health/nutrition 数值拆 typed child relations，但必须保持 revision/admission 与事务边界；不能把未定义 payload 留给 LLM。

### S15 `factset_revisions` — B→I（仅 SEALED 成为 canonical history）

- **作用/字段：** factset_id、status=BUILDING/READY/SEALED/STALE/ABANDONED、captured_input_frontier、captured_epoch、parent_factset_id、storage_mode=FULL/DELTA、delta_depth、member_revision、completed_member_revision、membership_digest、completion_certificate、association/admission/mapping basis、knowledge boundary、effective scope、sealed_at。
- **约束：** DB：ID 唯一，canonical 引用目标必须 SEALED。TX：BUILDING 唯一 builder 可写；READY 固定成员/摘要，未成为 canonical；T2-SEAL 复核 frontier/epoch/完成凭据后原子封存+切 S01 head。SEALED 不可编辑；重复 seal 不重新切旧 head；失败保留原 head。
- **索引：** subject/status/created_at（清理 build）；subject/known_at（SEALED）；parent_factset_id。
- **唯一写入所有者：** CanonicalViewService.BeginBuild/WriteCandidate/CompleteFactset 只写 build；SealFactset 独占 T2-SEAL。构建不持 S01 长锁。
- **映射：** INV-03, INV-05, INV-06, INV-07, INV-16, INV-17；T2（SEAL）, T3。

### S16 `factset_members` — B→I（仅父对象 SEALED 后）

- **作用/字段：** factset_id、member_operation=SET/REMOVE、member_kind、类型化 fact/admission/association/mapping revision 引用、logical_member_key、action_scope；REMOVE 是 tombstone。
- **约束：** DB：factset/kind/logical_member_key/scope 唯一；引用同主体且类型匹配。TX：仅父 BUILDING 可写；写成员与推进 member_revision 同一 build 事务；Complete 与 writer 在同一 build gate 串行化；READY/SEALED 禁止增删改。所有 canonical reader 排除未 SEALED 成员。
- **索引：** factset/kind/logical_member_key；被引用 revision 的反向索引。
- **唯一写入所有者：** CanonicalViewService.WriteCandidate；不由 SealFactset 批量写 members。
- **映射：** INV-03, INV-05, INV-06, INV-16, INV-17；T2（SEAL/read guard）, T3。

### S17 `control_events` — I

- **作用/字段：** control_id、control_revision、kind（HOLD/STOP/OVERRIDE/RESTRICTION/CLEAR）、scope、command/evidence/admission refs、policy、effective/known times、review_due_at、previous_event_id。
- **约束：** DB：control/revision 唯一、CLEAR 必须引用被解除对象及 clearance basis。DOMAIN：普通文本/摘要不能产生 command authority。TX：改变执行权限与 epoch 同事务。
- **索引：** subject/control/revision；subject/scope/known_at；关联 evidence_id。
- **唯一写入所有者：** ControlService.ApplyControl / ClearControl（同一 writer）；紧急路径可先 hold 再完整解析。
- **映射：** INV-02, INV-08, INV-09, INV-10, INV-15, INV-16；T2。

### S18 `control_heads` — M，同步投影

- **作用/字段：** subject/control_id、last_event_id/revision、current state、execution_scope、review_due_at。
- **约束：** DB：subject/control_id 唯一。TX：与 S17 同事务更新；不能靠异步消费者更新执行安全状态。失配或不可验证时 authorization fail closed，不从缓存推导已解除。
- **索引：** subject/active-state/scope；待 review 时间（仅调度，不自动清除）。
- **唯一写入所有者：** ControlService；可从 S17 重建但重建期间不得错放行。
- **映射：** INV-08, INV-09, INV-10；T2, T6, T7。

### S19 `exercise_catalog_revisions` — I

- **作用/字段：** namespace、exercise_identity、revision、movement/equipment/unit semantics、compatibility、known_at。
- **约束：** DB：namespace/exercise/revision 唯一；个人 catalog 受主体隔离，全局 catalog 只读。DOMAIN：不同器械/load convention 不因名称相近自动兼容。
- **索引：** namespace/exercise/revision；movement/equipment 用于 bounded catalog search。
- **唯一写入所有者：** ExerciseCatalogService.PublishRevision；被采用为用户输入的变化经 T2 分类/失效。
- **映射：** INV-02, INV-05, INV-06, INV-16；T2, T3。

### S20 `exercise_mapping_decisions` — I

- **作用/字段：** source_exercise_identity、catalog_revision_id、mapping scope、ACCEPTED/UNRESOLVED/RETRACTED、policy/method、approval ref、supersedes、known/effective times。
- **约束：** DB：mapping family/revision 唯一、catalog FK。TX：当前采用映射经 factset 明确选择；模糊映射不直接进入 sequence/progression qualification。
- **索引：** subject/source_exercise/known_at；catalog_revision_id；supersedes_id。
- **唯一写入所有者：** ExerciseMappingService.DecideMapping。
- **映射：** INV-02, INV-05, INV-06, INV-16；T2, T3。

### S21 `projection_versions` — I

- **作用/字段：** projection_kind、engine artifact、input_basis_hash、window、typed result、quality/coverage、computed_at、validity boundary。
- **约束：** DB：subject/kind/engine/basis/window 的计算身份唯一或幂等；DOMAIN：Exposure 上下界与 unknown 分离，sequence 只由已准入 actual 计算。不得用 computation time 冒充输入 known time。
- **索引：** subject/kind/basis_hash；window end；engine version 反向影响查询。
- **唯一写入所有者：** ProjectionService.RecordResult；T3 准备阶段独立短事务，完成不更新 S01 generation。
- **映射：** INV-03, INV-04, INV-06, INV-07, INV-16；T3。

### S22 `projection_dependencies` — I

- **作用/字段：** projection_id、dependency_kind、明确 FK（factset/fact revision/mapping/catalog/program/policy）、collection predicate signature、collection revision/digest、query window。
- **约束：** DB：projection/dependency semantic key 唯一，闭合 target kinds 与对应 FK。DOMAIN：同时保留正依赖和 absence/集合依赖；不宣称列几个读取行就足以覆盖新增记录。
- **索引：** 各 dependency target 的反向索引；projection_id；kind/collection signature。
- **唯一写入所有者：** ProjectionService，与 S21 结果封存同事务。
- **映射：** INV-05, INV-06, INV-07, INV-16；T2, T3。

### S23 `manifest_builds` — B

- **作用/字段：** build_id、captured_factset/frontier/epoch/program/policy、candidate binding refs、BUILDING/READY/STALE/FAILED/PUBLISHED、error_code。
- **约束：** DB：build_id 唯一；完成的 candidate 内容不可在 READY 后偷偷改变。TX：PUBLISHED 只在生成 S24 的 T3 内发生；旧 epoch build 不能重贴 epoch。
- **索引：** subject/build status/created_at；captured input frontier。
- **唯一写入所有者：** DecisionPublicationService.Build / Publish。
- **映射：** INV-06, INV-07, INV-10, INV-17；T3。

### S24 `decision_manifests` — I

额外绑定 artifact_roots、dependency_closure_hash、registry_revision_at_publish；发布 guard 读取当前 registry，不能只保存历史 revision。

- **作用/字段：** build_id、generation、factset_id、input_frontier_hash、program/policy/catalog/mapping bindings、captured_epoch、source watermarks、local_date/calendar policy、valid_until、manifest_hash。 artifact_roots、artifact_dependency_closure_hash、registry_revision_at_publish。
- **约束：** DB：subject/generation 唯一、build_id 唯一、所有主体引用匹配、valid_until 晚于发布时间。TX：完整 basis、epoch、当前 Program/policy 复核后与 S01 pointer/generation 同事务提交。
- **索引：** subject/generation；subject/published_at；captured_epoch；factset_id。
- **唯一写入所有者：** DecisionPublicationService.PublishManifest。
- **映射：** INV-05, INV-06, INV-07, INV-09, INV-10, INV-16；T3, T6。

### S25 `manifest_projection_bindings` — I

- **作用/字段：** manifest_id、projection_role、projection_id 或显式 unavailable_reason、validated_basis_hash。
- **约束：** DB：manifest/role 唯一，projection 与 unavailable 二选一。TX/DOMAIN：必须角色齐全，basis 兼容；缺失不是零。与 Manifest 同事务封存。
- **索引：** manifest/role；projection_id 反向定位受影响历史。
- **唯一写入所有者：** DecisionPublicationService.PublishManifest。
- **映射：** INV-04, INV-05, INV-06, INV-07, INV-10；T3。

### S26 `decision_snapshots` — I

- **作用/字段：** attempt_id、manifest_id、request_revision_id、captured_epoch、mandatory context payload/hash、context-builder version、token accounting、source cutoff。
- **约束：** DB：attempt/snapshot sequence 唯一；引用同主体。DOMAIN：mandatory evidence 不被静默裁剪；命令权限与推断摘要类型固定。重建内容产生新 snapshot，不改原记录。
- **索引：** attempt_id；manifest_id；context_hash 仅作同主体缓存识别。
- **唯一写入所有者：** ContextService.RecordSnapshot；T4/T5 准备阶段受 attempt guard 保护。
- **映射：** INV-05, INV-10, INV-13, INV-15, INV-16；T4, T5, T6。

### S27 `planning_intents` — M

- **作用/字段：** purpose/date/calendar scope、root_request_id、status、current_request_revision_id、current_attempt_id、deadline、lease_owner/expires_at、fence_token、各维度 root limits/reserved/settled counters、stale_restart_count、result_bundle/auth refs。
- **约束：** DB：同主体/date/purpose 的 ADMITTED/RUNNING intent 唯一；root request 自然身份唯一；计数非负。TX：budget aggregate 原子占用，终态不可重开，request 更新不重置预算/deadline。
- **索引：** active partition 唯一索引；status/deadline；status/lease expiry 供 reaper 发现候选。
- **唯一写入所有者：** PlanningWorkflowService；late settlement 仅经限定账本入口更新核算字段，不复活 intent。
- **映射：** INV-10, INV-11, INV-12, INV-13, INV-17；T4, T5, T6, T8。

### S28 `planning_request_revisions` — I

- **作用/字段：** intent_id、revision、normalized constraints、constraint_fingerprint、calendar policy、command_receipt_id、origin actor/trigger。
- **约束：** DB：intent/revision 唯一；request_hash 与 canonical normalization version 绑定。TX：写新行与 S27 当前指针切换同 T4，旧 attempt 即刻失权。
- **索引：** intent/revision；intent/fingerprint（不要求永久唯一，因为用户可改回旧约束）。
- **唯一写入所有者：** PlanningWorkflowService.AdmitOrReviseIntent。
- **映射：** INV-10, INV-11, INV-13；T4, T6。

### S29 `planning_attempts` — M，执行元数据

- **作用/字段：** intent_id、attempt_no、request_revision_id、manifest/snapshot_id、captured_epoch、fence_token、status、model/prompt/tool/runtime artifact versions、failure_code、started/completed times。
- **约束：** DB：intent/attempt_no 唯一。TX：写入阶段校验 intent/request/fence/lease；terminal attempt 不恢复。proposal 正文单独存 S34，不能用 attempt 更新覆盖模型输出历史。
- **索引：** intent/attempt_no；status/updated_at；manifest_id。
- **唯一写入所有者：** PlanningWorkflowService.AdvanceAttempt；worker 仅调用命令。
- **映射：** INV-10, INV-11, INV-12, INV-13, INV-14, INV-17；T4, T5, T6, T8。

### S30 `planning_quota_buckets` — M

- **作用/字段：** subject、quota_kind、UTC window start/end、policy_version、admitted_count、limit。
- **约束：** DB：subject/kind/window/policy 唯一。TX：新 intent 与额度扣减同 T4；修改 request 不新扣 root 配额也不恢复原配额。
- **索引：** quota 唯一键；window_end 供保留策略。用户级配额不取代系统/provider 容量控制。
- **唯一写入所有者：** PlanningWorkflowService.AdmitIntent。
- **映射：** INV-11, INV-13；T4。

### S31 `call_reservations` — M，状态与核算投影

- **作用/字段：** intent/attempt_id、operation_slot、provider/model/config fingerprint、reserved amounts、price-accounting version、status、dispatch_owner/fence/permit_id、provider_request_id（可空）、actual_usage、settlement_revision。
- **约束：** DB：intent/attempt/operation_slot 唯一，reservation ID 唯一；状态 enum 闭合。TX：原子预留后才允许 DISPATCH_INTENT；只有 RESERVED 可取消退款；网络未知不能重置为 RESERVED。
- **索引：** intent/status；status/last_transition_at；provider/request_id（有可靠身份才唯一，不能以空值构造身份）。
- **唯一写入所有者：** CallLedgerService.Reserve / PermitDispatch / CancelUndispatched / Settle / MarkUnknown；业务字段修改受 PlanningWorkflow 协调。
- **映射：** INV-11, INV-12, INV-17；T5, T8。

### S32 `call_ledger_events` — I

- **作用/字段：** reservation_id、transition_revision、event_type、amount deltas、receipt/reconciliation source、dispatch permit identity、occurred/recorded times。
- **约束：** DB：reservation/transition_revision 唯一、可靠 settlement receipt 唯一。TX：与 S31 状态、S27 预算 counter 同事务；结算重复回执无双重扣减/释放。
- **索引：** reservation/revision；intent correlation；receipt identity。
- **唯一写入所有者：** CallLedgerService；旧 worker 仅能提交绑定 reservation 的证据给结算入口，不能任意设置 terminal/result。
- **映射：** INV-11, INV-12, INV-16；T5, T8。

### S33 `tool_evidence_records` — I

- **作用/字段：** attempt/snapshot_id、tool_name/version、arguments hash/payload、query scope/window、input revision refs、result hash/blob、coverage/truncation、trust_class、start/end times。
- **约束：** DB：attempt/tool_operation_slot 唯一或记录重试序号；scope 必须同主体。DOMAIN：结果能回溯固定 Manifest；live 输入未绑定则不准采用。
- **索引：** attempt/operation_slot；snapshot_id；result_hash 仅同主体。
- **唯一写入所有者：** ContextToolGateway.RecordResult；读取与记录属于 T5 工作阶段，不持用户锁等待远端。
- **映射：** INV-05, INV-10, INV-15, INV-16, INV-17；T5。

### S34 `proposal_revisions` — I

- **作用/字段：** proposal_family/revision、attempt/snapshot、kind=FITNESS/NUTRITION/BLUEPRINT、payload/hash、producer artifact、citations、parent proposal（修复）、fitness_proposal_id/hash 与 demand_feature_id/hash（Nutrition 必填）。
- **约束：** DB：family/revision 唯一、kind 与必填依赖一致、类型化 FK、same subject。DOMAIN：proposal 不含实际完成事实或批准权限；重新修复创建新 revision。
- **索引：** attempt/kind/revision；fitness_proposal_id；demand_feature_id。
- **唯一写入所有者：** ProposalService.RecordProposal；模型输出由服务器验证后记录，无 canonical write capability。
- **映射：** INV-01, INV-02, INV-13, INV-14, INV-15；T5, T6。

### S35 `prescription_demand_features` — I

- **作用/字段：** fitness_proposal_id/hash、method version、feature payload/hash、逐字段 semantic class、估计区间、window/basis。
- **约束：** DB：Fitness/method/basis 唯一；code-computed producer，不接受模型填充事实元数据。DOMAIN：PRESCRIBED_QUANTITY/TARGET/ESTIMATE 分离，不当作实际生理消耗。
- **索引：** fitness_proposal_id；content_hash。
- **唯一写入所有者：** DemandFeatureService.ComputeAndRecord；不推进 Manifest generation。
- **映射：** INV-01, INV-02, INV-07, INV-14；T5, T6。

### S36 `evidence_resolutions` — I

- **作用/字段：** manifest_id、action_type/parameters hash、exercise identity、resolver/policy version、support/contradiction/association refs、coverage、consistency、truncation、query basis hash、resolution expiry。
- **约束：** DB：动作与 manifest/policy 绑定。DOMAIN：权威 resolver 从政策范围计算，不由 Agent citations 构造。覆盖完整与无冲突是不同维度；结果 hash 相同不能证明适用于另一动作。
- **索引：** subject/manifest/action fingerprint；被影响 evidence revision 的可定位引用。
- **唯一写入所有者：** EvidenceResolver.ResolveActionEvidence；T6 准备阶段，最终提交复核 basis。
- **映射：** INV-02, INV-03, INV-04, INV-05, INV-09, INV-16；T6。

### S37 `validation_results` — I

- **作用/字段：** attempt、request_revision、manifest/epoch、proposal hashes、demand hash、resolver results、policy_bundle、execution_basis_event_id 及相关 execution/head 修订、PASS/FAIL/REVIEW、codes、valid_until、validator artifact。
- **约束：** DB：validation identity 唯一、明确目标 FK。DOMAIN：逐项验证/证据义务。TX：PASS certificate 只有全部 binding 仍匹配才可消费；不是 bearer authorization。
- **索引：** attempt/result；manifest_id；policy_bundle_id；失败码统计索引按实际查询决定。
- **唯一写入所有者：** ValidationService.RecordResult；最终 T6 提交命令不能省略 guard。
- **映射：** INV-02, INV-05, INV-09, INV-10, INV-13, INV-14；T6。

### S38 `daily_plan_heads` — M

- **作用/字段：** subject/local_date、calendar_policy、current_bundle_revision_id、head_revision、day lifecycle。
- **约束：** DB：subject/local_date 唯一。TX：唯一 active bundle 由此指针表达；旧 bundle 不覆写，切换与新处方/授权/intent success 同 T6；不能维护两个各自可写的 ACTIVE 真相。
- **索引：** 唯一 subject/local_date；current_bundle_revision_id。
- **唯一写入所有者：** PrescriptionCommitService.CommitBundle；取消/关闭同一 writer 由明确控制命令调用。
- **映射：** INV-09, INV-10, INV-13, INV-14；T2, T6, T7。

### S39 `daily_bundle_revisions` — I

- **作用/字段：** day scope、revision_no、parent_revision_id、intent/attempt/manifest、commit_receipt_id、generation_mode、content_hash、validation_result_id。
- **约束：** DB：subject/date/revision 唯一、commit receipt 唯一。TX：内容、成员、授权全部成功才切换 head。REUSED_VALID_PLAN 可返回现有 bundle 而不制造无内容变化的 revision。
- **索引：** subject/date/revision；intent_id；manifest_id。
- **唯一写入所有者：** PrescriptionCommitService.CommitBundle。
- **映射：** INV-09, INV-10, INV-13, INV-14, INV-16；T6。

### S40 `prescription_revisions` — I

- **作用/字段：** prescription_identity/revision、kind=TRAINING/NUTRITION、typed content、source proposal/fallback template、content_hash、hash_scheme_version。
- **约束：** DB：subject/prescription/revision 唯一、kind 与 typed payload 一致。DOMAIN：已验证内容；不存可写 authorization_status。相同内容重新授权不强制创建新处方。
- **索引：** identity/revision；subject/content_hash（不跨用户复用身份）。
- **唯一写入所有者：** PrescriptionCommitService；draft/proposal 留在 S34，不把未验证流式片段放入 executable registry。
- **映射：** INV-01, INV-02, INV-09, INV-14, INV-16；T6。

### S41 `bundle_prescription_members` — I

- **作用/字段：** bundle_revision_id、prescription_revision_id、kind、session_slot、order。
- **约束：** DB：bundle/kind/slot 唯一、kind 与处方复合引用一致。V1 TRAINING 只允许单个明确 slot，NUTRITION 只允许一个 daily slot；以关系唯一性与 allowed-slot 检查表达，不仅在 UI 限制 count。
- **索引：** bundle/kind；prescription_revision_id。
- **唯一写入所有者：** PrescriptionCommitService，与 S39/S40 同 T6。
- **映射：** INV-09, INV-14；T6, T7。

### S42 `authorization_issuances` — I

额外绑定 artifact closure、registry_revision_at_issue、validity_certificate（每项依赖身份/修订/期限或批准的 TIMELESS、计算版本、摘要）。valid_until 是闭包最早到期，不能晚于任一关键依赖。不可原地延长。

- **作用/字段：** prescription_revision_id/bound_hash、manifest/epoch、policy、validation_result_id、scope、valid_from/until、issuance_reason、issuing_command_id。 artifact_dependency_closure、registry_revision_at_issue、validity_certificate（依赖 identity/revision/validity、计算版本与 closure digest）。
- **约束：** DB：issuance id 唯一、command/处方/scope 唯一、处方与 hash 绑定、有效期行内检查。TX：完整最新签发 guard。A1 与 A2 可绑定同一 P；禁止更新旧 A 的有效期或“恢复”历史。
- **索引：** subject/prescription/scope/issued_at；subject/epoch；valid_until 仅筛选候选。
- **唯一写入所有者：** AuthorizationService.Issue，必须被 T6 CommitBundle/Reauthorize 命令原子调用，不能开放通用 INSERT API。
- **映射：** INV-02, INV-08, INV-09, INV-10, INV-16；T6, T7。

### S43 `authorization_events` — I

- **作用/字段：** authorization_id（定向事件）或 invalidated_epoch/scope（用户屏障事件）、event_kind、cause_control/admission/command、recorded time。
- **约束：** DB：事件 target 类型闭合且互斥、幂等因果键。TX：屏障变更和 S01 epoch 同事务；定向 suspension/revocation 经同一协调锁。禁止 RESTORE_VALID 事件。
- **索引：** subject/authorization_id/event time；subject/invalidated_epoch；cause id。
- **唯一写入所有者：** AuthorizationService.Invalidate，受 T2 control/admission 命令调用。
- **映射：** INV-08, INV-09, INV-10, INV-16；T2, T6, T7。

### S44 `workout_sessions` — M，实际会话身份与生命周期

- **作用/字段：** session_id、underlying_event_id、origin=APP_STARTED/EXTERNAL_REPORTED、lifecycle、start/completion times、latest_actual_fact_revision_id、execution_revision。
- **约束：** DB：subject/session 唯一；当前确认关联的 event/session 身份不得重复。TX：START 受 T7 guard；外部实际训练由 T2 接受，无授权也可保存。实际 set/bout 修订在 S14，不覆写原事实。
- **索引：** subject/start time；underlying_event_id；subject/in-progress state。
- **唯一写入所有者：** ExecutionService，通过 Start/Resume 或 AcceptExternalExecution 调用；identity correction 保留 alias/association 历史，不删除旧实体。
- **映射：** INV-01, INV-03, INV-09, INV-16, INV-18；T2, T7。

### S45 `execution_bindings` — I

- **作用/字段：** session_id、binding_revision、kind=START/RESUME、prescription_revision_id、authorization_id、accepted_at、command_receipt_id、execution_scope。
- **约束：** DB：session/binding_revision 唯一、START 每 session 最多一条、P/A 主体与内容关联匹配。TX：当前资格通过才写；外部训练无有效 A 时不伪造 binding，S44.origin 表达其来源。
- **索引：** session/binding_revision；authorization_id；prescription_revision_id。
- **唯一写入所有者：** ExecutionService.StartSession / ResumeSession。停止与完成事件保存在 S03，原绑定不被更新为新 A。
- **映射：** INV-09, INV-10, INV-16, INV-18；T7。

### S46 `replay_runs` — M，隔离 evaluation 存储

- **作用/字段：** replay_mode、knowledge_cutoff、release_bundle_id、historical_manifest_id、evaluation_subject、status、input selection hash、randomness/available-model limitations。
- **约束：** DB：run_id 唯一；有显式 mode/cutoff；无可写 production FK target。DOMAIN：cutoff tool policy 全链路一致；权限角色不可写 live 命令。
- **索引：** release/mode/cutoff；status。
- **唯一写入所有者：** ReplayService；不是 T6 生产提交路径。
- **映射：** INV-15, INV-16, INV-17；T1–T8 的只读历史重建，不加入 live 事务。

### S47 `replay_artifacts` — I，隔离 evaluation 存储

- **作用/字段：** replay_run_id、artifact_kind、input/derived/output payload/hash、source revision refs、included/excluded reasons、leakage audit、simulation marker。
- **约束：** DB：run/artifact identity 唯一。DOMAIN：区分 RECORDED_OUTPUT 与 FRESH_MODEL_RUN；artifact 缺失返回明确错误。模拟 authorization 不进入 S42。
- **索引：** run/kind；source reference 仅用于获准的历史读取。
- **唯一写入所有者：** ReplayService.RecordArtifact。
- **映射：** INV-02, INV-15, INV-16；T1–T8 的只读历史重建，不加入 live 事务。

### S48 `evaluation_releases` — I

- **作用/字段：** release_id、model/prompt/engine/policy artifact bundle、dataset/split ids、freeze times、metrics/threshold config、evaluation report refs、rollout decision provenance。
- **约束：** DB：release identity 唯一。DOMAIN：评测报告与用于生产的制品精确绑定；若无实测结果，不可声明 PASSED。修改阈值或模型产生新 release。
- **索引：** release id；artifact hashes；recorded_at。
- **唯一写入所有者：** ReleaseEvaluationService.RecordRelease；生产选择此 release/policy 仍经 T2 用户激活入口。
- **映射：** INV-02, INV-09, INV-15, INV-16；T2（激活绑定）；evaluation 独立运行。

### S49 `safety_artifacts` — I（全局 namespace）

- **作用/字段：** artifact_id、artifact_kind、content_hash、declared_dependency_ids、validity_spec、TIMELESS approval policy/reason（如适用）、registered_at、registrar_identity。与 S05/S19/S48 中制品有确切身份绑定。
- **约束：** DB：kind/content identity 唯一；identity 不可复用。DOMAIN：依赖为已注册 identity，无环、完整且有界；未知/缺失 validity 不具准入资格。依赖引用不得藏于自然语言；DDL 可规范化为 child edges，不改变逻辑含义。
- **索引：** artifact_id；kind/content_hash；dependency identity 反向检索（审计/影响分析，不要求逐用户撤销）。
- **唯一写入所有者：** SafetyRegistry.RegisterArtifact（独立管理命令）；禁止普通 Agent/user writer 注册或修改。新注册与 T3/T6/T7 的可见性通过 registry gate 协调。
- **映射：** INV-02, INV-08, INV-09, INV-10, INV-16；T2（GLOBAL）, T3, T6, T7。

### S50 `artifact_revocation_events` — I（全局 namespace）

- **作用/字段：** revocation_id、artifact_id、registry_revision、effective_at、recorded_at、reason_code、operator/capability identity、command_key/request_hash、causation incident、outbox delivery identity。
- **约束：** DB：command identity 唯一、artifact 引用 S49。TX：T2-GLOBAL 追加与 S51 revision/receipt 原子；撤销只能收缩，不恢复旧 identity。重复同 key/hash 返回原结果，不同 hash 拒绝。
- **索引：** artifact_id（任何撤销即 deny）；registry_revision（同步/audit）；operator/recorded_at。
- **唯一写入所有者：** SafetyRegistry.RevokeArtifact，独立 emergency capability；不调用模型、不取用户 S01、不逐用户写 S43。全局 receipt/event 放在此管理 namespace，不伪造 subject_id。
- **映射：** INV-02, INV-08, INV-09, INV-10, INV-16；T2（GLOBAL）, T3, T6, T7。

### S51 `safety_registry_state` — M（全局协调点）

- **作用/字段：** registry_scope（V1 单一 system scope）、registry_revision、last_revocation_id；共享/排他 gate 的逻辑协调身份。
- **约束：** DB：scope 唯一。TX：管理变更取排他 gate；T3/T6/T7 取共享 gate并读取取得 gate 后已提交的撤销；revision 与 S50 原子更新。不要求 A.captured_revision 等于当前值，不因无关撤销失权。
- **索引：** registry_scope 主键；禁止每次准入更新同一全局计数器。
- **唯一写入所有者：** SafetyRegistry 管理入口；用户 STOP / 输入接收 / reaper 不依赖此 gate。审计查询缓存不授予执行资格。
- **映射：** INV-08, INV-09, INV-10, INV-17；T2（GLOBAL）, T3, T6, T7。

## 3. 唯一 command/write entrypoint、幂等与错误

下表的 owner 是唯一逻辑写入服务，不要求变成独立微服务。内部 helper 不得绕过该入口的 actor/subject/guard。所有 prep-result 写入是独立短事务，T 编号表示所属协议阶段，绝不意味着从准备开始一直保持事务。

| Command | Owner / transaction | 幂等身份 | 必须拒绝的典型错误 |
|---|---|---|---|
| ReceiveEvidence | EvidenceService / T1 | source object + reliable revision，或 adapter observation key | SOURCE_IDENTITY_CONFLICT、SUBJECT_MISMATCH |
| RecordCandidate | ExtractionService / T1 后准备阶段 | evidence revision + extractor version + extraction operation | PROVENANCE_MISSING、ASSERTION_SCHEMA_INVALID |
| DecideAssociation / DecideAdmission / AcceptFactRevision | 对应 S12/S13/S14 writer；CanonicalInputCoordinator 原子编排 T2 | command key + expected current input/basis + payload hash | BASIS_STALE、ADMISSION_CONFLICT、EVENT_ASSOCIATION_AMBIGUOUS |
| ApplyControl / ClearControl | ControlService / T2 | explicit command key；自动 hold 用 risk evidence + policy + scope | COMMAND_NOT_AUTHORIZED、CLEARANCE_INSUFFICIENT |
| ApproveChange / ActivateApprovedProgram | ApprovalService / ProgramService / T2 | approval command；activation bound approval + exact proposal revision | APPROVAL_STALE、APPROVAL_CONTENT_MISMATCH、POLICY_DISABLED |
| RecordProjection / BuildManifest | ProjectionService / PublicationService / T3 准备阶段 | type + engine + exact basis；build key | DEPENDENCY_UNAVAILABLE、BASIS_INCOMPATIBLE |
| PublishManifest | DecisionPublicationService / T3 | build_id（自然唯一）+ command key | BUILD_STALE、EPOCH_MISMATCH、POLICY_MISMATCH |
| AdmitOrReviseIntent | PlanningWorkflowService / T4 | client request key，不以 date/purpose 替代 | QUOTA_EXHAUSTED、INTENT_TERMINAL、REQUEST_CONFLICT |
| AcquireLease / RenewLease | PlanningWorkflowService / T5 | lease-operation key + expected owner/fence | LEASE_LOST、DEADLINE_EXCEEDED |
| ReserveCall / PermitDispatch | CallLedgerService / T5 | intent + attempt + operation slot；permit key | BUDGET_EXHAUSTED、FENCE_MISMATCH、DISPATCH_ALREADY_POSSIBLE |
| RecordToolResult / RecordProposal / RecordDemandFeatures | S33/S34/S35 writer / T5 准备阶段 | attempt operation slot + artifact version | SNAPSHOT_STALE、DEPENDENCY_HASH_MISMATCH |
| ResolveEvidence / RecordValidation | S36/S37 writer / T6 准备阶段 | action/manifest/policy/basis fingerprint | EVIDENCE_INSUFFICIENT、COVERAGE_INCOMPLETE、POLICY_UNCONFIGURED |
| CommitBundle / Reauthorize | PrescriptionCommitService + AuthorizationService / T6 | commit command key + intent/result fingerprint | REQUEST_STALE、FENCE_MISMATCH、EPOCH_MISMATCH、HOLD_ACTIVE、AUTH_SCOPE_DENIED |
| StartSession / ResumeSession | ExecutionService / T7 | authenticated command key + session ID + binding revision | AUTH_EXPIRED、AUTH_REVOKED、CONTENT_MISMATCH、EXECUTION_CONFLICT |
| RecordActualExecution / CompleteReportedWorkout | CanonicalFactService + ExecutionService / T2 | source observation / actual report key | SOURCE_IDENTITY_CONFLICT；不能因无授权而拒收事实 |
| CancelIntent | PlanningWorkflowService / T4 或 T8 | cancel command key + intent ID | 已完成则返回已完成事实，不伪造撤销旧成功 |
| SettleCall / MarkUnknown / ReapIntent | CallLedgerService / WorkflowService / T8 | provider receipt；reservation + expected transition；intent + expected fence/deadline | SETTLEMENT_CONFLICT、STALE_REAPER_CANDIDATE |
| RunReplay / RecordRelease | ReplayService / ReleaseEvaluationService | mode/cutoff/release/input-run key | KNOWLEDGE_BOUNDARY_VIOLATION、ARTIFACT_UNAVAILABLE |

**共同错误：** IDEMPOTENCY_KEY_REUSE_WITH_DIFFERENT_PAYLOAD、SUBJECT_MISMATCH、INVALID_TRANSITION、CONFIG_UNAVAILABLE。错误码不允许直接暴露其他主体对象是否存在。

**错误重试：** timeout/deadlock/serialization retry 是基础设施失败，可在 deadline 与有限次数内重试整个短事务并重读 guard；guard rejection 不是数据库重试。STALE 只能由 workflow 明确产生新 attempt，消耗原预算。不存在“所有 409 都重试”的统一策略。

**幂等 replay：** 同 key 同 payload 重复命令返回原结果身份及 `replayed=true`。历史上 START 成功不表示现在仍可继续执行，响应另外计算当前 authorization eligibility。客户端不能把重放旧成功当作新一次许可。

**发送许可特殊规则：** 只有成功把 RESERVED 变成 DISPATCH_INTENT 的首次 transition winner 可执行那一次网络调用。PermitDispatch 的幂等重复结果只能用于查账，必须标记不可再次发送；不得因拿到同一 permit 响应又调用 provider。

**receipt 保留：** 对收到确认的持久业务命令，使用自然唯一键（build_id、commit identity、session binding、source revision）作为第二道防重放；清理 receipts 不清理这些约束。无法保留自然身份的命令，保留不可重放 tombstone 或显式关闭已过期 key namespace。未知 request key 不自动等于合法新授权。

**Reauthorize：** 使用新的、已准入的 planning/revalidation intent；可不调用模型，但仍满足 T6 的 current attempt/manifest/epoch/deadline guard。不能重新打开原终态 intent，也不能绕过 hold 或最新 Manifest。

## 4. 固定锁序与读写边界

### 4.1 V1 锁序

```text
registry gate S51（仅 T3/T6/T7，共享；全局管理独占且不取 S01）
  → subject coordination row S01
  → relevant user quota buckets S30（稳定 key 排序）
  → planning intent S27（如多个，按稳定 ID 排序）
  → reservations S31（按稳定 ID 排序）
  → daily head S38
  → execution aggregate S44
  → exact command receipt / remaining aggregate rows
```

事务只取实际需要的锁，但不能逆序。所有 unique-key 竞争也在这一协议下处理；特别是不得先抢 receipt 的唯一键再等待另一个事务已持有的 S01。T1 原始接收仅处理来源幂等且不再反向取得 S01；需要紧急 hold 时由另一个 T2 事务处理。

用户安全入口应在 raw evidence 可用后立即执行 T2。若产品要求“风险提交成功”意味着 hold 已生效，则 API 必须等 T2 成功再确认该语义；T1 成功只能表示已收件，不能宣称安全措施已落实。

同用户锁仅覆盖毫秒级目标的短事务；这里是性能目标而非已测 SLA。不得在其中进行模型调用、外部文件获取、完整历史 resolver、投影计算或大范围重建。

PostgreSQL 行锁与事务结束相关，死锁仍可能发生；固定顺序降低交叉持锁风险，数据库中止后必须重试完整事务而非沿用旧 guard。[PostgreSQL Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)

没有 registry 依赖的事务直接从 S01 开始，且不能再反向申请 S51。Factset build 事务只锁 build，不锁 S01；T2-SEAL 按 S01→build 获取，READY 内容已固定，不扫描 member。全局 registry 控制不使用用户 subject receipt；S50 带管理命令幂等身份。

全局 revoke 与 publish/issue/START 的通过/拒绝以受 gate 保护的原子提交顺序为准；锁前缓存/快照无效。物理 SQL 必须确保取得 gate 后的读取看见先前已提交撤销。registry 不可读或 gate 超时则 deny；用户 STOP 继续走独立 S01 通道。

### 4.2 队列与 reaper

扫描 lease/deadline/outbox 索引只用于发现候选。reaper 不应持住 intent 行再反向申请 S01；先无锁读取候选 ID，随后按统一顺序锁住并重检 fence/status/deadline。过时扫描结果返回 STALE_REAPER_CANDIDATE。

OutboxDispatcher 在自己的 claim/delivery 事务中不能获取业务 S01。业务消费者调用新幂等命令，不携带 outbox 行锁跨入业务写入。队列可重复，业务结果不得重复。

### 4.3 时间、快照与副本

时间 guard 在获得协调锁后读取可信数据库/服务端时间，不能使用在排队前保存的时间证明 lease 尚有效。guard acceptance time 记录到事件；响应发出时若授权已过期，仍需明确不可执行，不把历史成功缓存成当前许可。

历史/工具读取可使用短一致事务取得 input revisions 与数据，或直接读取不可变引用；长时间推理不持 MVCC snapshot。只读副本可用于允许陈旧的展示，但 epoch/fence/START/commit 的权威 guard 必须读取主协调存储。

## 5. T1–T8 事务落点

| Tx | 必须原子完成的读写 | 提交前 guard | 显式排除 |
|---|---|---|---|
| T1 | S09 raw evidence + S02 receipt + S03/S04 接收事件；解析候选另开短事务写 S10 | subject/source idempotency、内容身份冲突 | 不接受未解析候选为训练成功；不重算特征 |
| T2 | IN：S12/S13/S14 或 S17/S18 + S01 frontier/epoch/basis + S43/events/receipt；SEAL：S15 READY→SEALED + S01 factset head/events/receipt；GLOBAL：S50 + S51 revision/管理 receipt；三者是独立原子命令 | IN：输入/actor/失效分类；SEAL：captured frontier/epoch/member revision/完成凭据；GLOBAL：管理 capability/identity + exclusive registry gate | 不把 IN 与 SEAL 假装跨构建原子；不在 S01 锁内批量写 S16；不逐用户 revoke |
| T3 | READY S23 guard；S24/S25 + S01 generation/current pointer + S23 published + S03/S04/S02 | sealed factset/input frontier、所有 dependency basis、当前 program/policy/epoch、validity、shared registry/current artifact eligibility | 不在事务内算 projection；不发布混合结果 |
| T4 | S30 准入配额、S27 intent、S28 request revision、S29 初始/失效状态、S02/S03/S04 | single-flight partition、request fingerprint、root admission limits | 不因改约束重置预算/deadline |
| T5 | lease/fence 变更；或 S31 reservation + S32 ledger + S27 counters；或 dispatch permit transition；均为独立短事务 | intent live、request revision、owner/fence/lease/deadline、预算余量 | 网络请求发生在 DISPATCH_INTENT 持久化之后、事务之外 |
| T6 | S39/S40/S41、S42、S38 head switch、S27 result/success、S29 committed、S02/S03/S04 | current snapshot/generation/epoch/request/fence/lease、policy、validation bindings、当前执行暴露、scope 和 active bundle、shared registry/current artifact eligibility、依赖有效期闭包 | 不靠 schema valid / validation PASS 单独放行；不先提交 bundle 再异步签授权 |
| T7 | S44 execution + S45 START/RESUME binding + S02/S03/S04 | 当前 A/P/content/scope、依赖有效期、epoch/holds、shared registry/current artifact eligibility、session lifecycle、重复 start | 不需要在线 LLM；不改历史 START 绑定 |
| T8 | S31/S32 与 S27 核算；或 reaper 对 S27/S29 的失权/终态；S02/S03/S04 | receipt identity、当前 reservation transition；或当前 fence/lease/deadline | 不恢复 unknown 预算；不让迟到响应恢复提交权限 |

T2-IN 保证 admission/correction 与必要失效同事务。T2-SEAL 是后续独立原子封存，不与输入事务捆绑。T2-GLOBAL 是全局管理事务。IN 后 SEAL 前旧 current_factset 允许保留供历史读取，但 T3 必须拒绝其落后 frontier；用户风险即时失效不等封存。

T6 的预算 guard 检查未超额、intent 未终止、deadline 未过；不要求必须还有剩余模型额度。恰好用完预算后得到有效结果仍可提交。只有需要继续搜索但没有预算，才进入 SEARCH_BUDGET_EXHAUSTED。

累计 exposure 验证结果同时绑定 S01.execution_basis_event_id。另一个 T6 计划提交、T7 START/RESUME/停止或 T2 实际执行更正使依据改变时，旧 validation 必须重新计算，不能因 Manifest/epoch 未变就复用。状态改变、对应 S03 事件与该指针在同一事务提交；本次 T6 先检查旧依据，提交新计划后推进该指针。这样避免两份各自通过、合起来超出 envelope 的并发提案。

### 5.1 四组强制交错

| 竞争 | 顺序 A | 顺序 B | 不允许的状态 |
|---|---|---|---|
| Publish vs Revoke | Publish 先提交 G，随后 revoke 推 epoch；G 不再可新签发 | Revoke 先提交，旧 build 的 epoch guard 失败 | 新 epoch 配旧内容的重贴标签 Manifest |
| START vs Revoke | START 先提交，保留 P/A 开始绑定；后续继续资格失效 | Revoke 先提交，START 返回 AUTH_REVOKED/EPOCH_MISMATCH | 已提交 revoke 后靠旧缓存成功 START |
| Cancel vs DISPATCH_INTENT | Cancel 先完成 RESERVED→CANCELLED，PermitDispatch 失败 | Dispatch permit 先完成，Cancel 结束 intent 但预留保留且远端可能继续 | 既释放预算又获得发送许可 |
| Lease takeover vs Commit | Commit 在 lease 有效时先成功；reaper 重检成功状态，不接管/改失败 | Takeover 先成功或 lease 已过；旧 fence commit 失败 | 旧 worker 晚返回覆盖新 worker 或复活终态 |

故障注入还需覆盖 COMMIT ACK 丢失、DISPATCH_INTENT 后尚未网络调用、网络调用后尚未写 DISPATCHED、写结算前进程退出。命令边界故障已有模型对应案例，实际进程/网络/数据库故障仍待执行；不视为真实并发证明。

## 6. 18 条 invariant 的强制位置

| Invariant | 主表落点 | 强制方式 | 验收证据 |
|---|---|---|---|
| INV-01 | S09,S10,S13,S14,S34,S35,S40,S44 | 事实/处方类型分离；准入禁止计划补全实际 | E01,A08 |
| INV-02 | S08,S10,S13,S17,S34,S36,S37,S42 | command capability 与模型输出隔离；唯一 writer | E08,E06 |
| INV-03 | S11,S12,S14,S16,S21 | underlying event identity + association policy + projection dedup | E03,E04 |
| INV-04 | S13,S14,S21,S25,S36 | 上下界/未知类型与 action-scoped admission | E05,E02 |
| INV-05 | S16,S22,S26,S33,S36,S37 | action-driven resolver + completeness/basis binding | E06,D03,D04 |
| INV-06 | S15,S16,S21,S22,S24,S25 | revision dependencies + collection/absence signatures | D02,D04 |
| INV-07 | S01,S21,S23,S24,S25 | generation 唯一 writer T3 + 原子发布 | D01,D05 |
| INV-08 | S01,S17,S18,S43,S49,S50,S51 | T2-IN/GLOBAL 独立同步屏障，不逐行等待旧 authorization 更新 | A01,A07,E02 |
| INV-09 | S37,S38,S40,S42,S43,S45,S49,S50,S51 | 内容/有效期闭包 + epoch/registry runtime guard + transaction | A03,A04,A05,A06 |
| INV-10 | S01,S24,S27,S28,S29,S42,S49,S50,S51 | epoch/request/fence/current manifest/current artifact 联合 guard | A02,D05,W05,W06 |
| INV-11 | S27,S30,S31,S32 | ledger + root counter 原子占用，SDK 物理调用全覆盖 | W01,W02,W03,W04 |
| INV-12 | S27,S31,S32 | UNKNOWN 占用与晚到结算权限隔离 | W01,W05,W06,W08 |
| INV-13 | S27,S28,S29,S37 | request revision 不可变、旧 attempt 提交失败 | W04 |
| INV-14 | S34,S35,S37,S39,S41 | 类型化依赖与 content hash 校验 | W07 |
| INV-15 | S09,S10,S26,S33,S34,S47 | summary 固定非命令；命令仅可来自专用入口 | E08,R04 |
| INV-16 | S09,S12,S13,S14,S20,S24,S42,S46,S47,S48 | 双时间/不可变版本 + cutoff-aware reads + eval 隔离 | R01,R02,R03,R04 |
| INV-17 | S01,S23,S27,S29,S31,S33 | 短事务；准备结果外算；dispatch 外部网络在事务外 | W01,W05,A07 + lock-duration instrumentation |
| INV-18 | S09,S14,S44,S45 | 外部 actual 不要求授权；缺绑定不能伪造 | A08,E01 |

仅“存在表/索引”不能证明 invariant 成立。所有 DOMAIN 判断必须有 fixture，所有 TX 判断必须在真实数据库的竞争与故障条件下验证。

## 7. 34 项验收的 Given / When / Then 与测试层级

PU = protocol unit/state-model；DC = 真 PostgreSQL 多事务并发；WF = worker/process fault injection；E2E = API→workflow→DB→UI eligibility。以下为 fixture 设计，不是可执行实现，也不是通过报告。

| ID | Given | When | Then | 层级 | 主表 |
|---|---|---|---|---|---|
| E01 | 处方 3 组，原文只完成 1 组 | 解析/准入/进阶 | 只有有证据的 actual，额外组不计完成 | PU,E2E | S10,S13,S14 |
| E02 | 风险通道收到尚未解析文本 | 解析不可用 | 适用 pending hold 生效，进阶被阻断 | PU,WF,E2E | S17,S18,S43 |
| E03 | 三来源指向一次训练 | 关联与 projection | 独立事件数 1，三来源仍留存 | PU,DC | S11,S12,S21 |
| E04 | 相近训练是否重复不明确 | reconciliation | 保留歧义，不强制合并/双计成功 | PU | S12,S36 |
| E05 | 完成量下界确定，上界未知 | 计算 exposure | 上界 unknown，不取计划值或零 | PU | S14,S21 |
| E06 | 成功后有反证，Agent 只引成功 | 解析加重义务 | Resolver 包含反证并按完整范围判断 | PU,E2E | S36,S37 |
| E07 | 原事实已用于授权 | 新更正撤回依据 | admission/epoch/投影资格变化原子生效 | DC,E2E | S13,S15,S01,S43 |
| E08 | 备注夹带批准指令，经多轮摘要 | context 与批准入口 | 保持非命令，不能产生 approval | PU,E2E | S10,S26,S08 |
| D01 | projection ready，Manifest 未发布 | 写计算结果 | generation 不变 | PU,DC | S21,S01 |
| D02 | 无关输入变化，进阶依赖未变 | BuildManifest | 复用原投影且 basis 验证通过 | PU | S22,S25 |
| D03 | 接受新输入但未发新 Manifest | tool live query | 不混入未绑定修订 | DC,E2E | S15,S24,S33 |
| D04 | 原查询不存在限制/相关事件 | 并发插入新记录 | 集合依赖或 epoch 捕捉变化 | DC | S22,S17,S01 |
| D05 | 旧 epoch 的 READY build | revoke 与 publish 交错 | 只允许 §5.1 两种合法结果 | PU,DC | S23,S24,S01 |
| A01 | 活跃计划可执行，模型服务故障 | revoke | 旧 A 立即失权，无需替代计划 | DC,WF,E2E | S01,S43 |
| A02 | epoch 已增加，Manifest 仍旧 | 重新签发相同 P | 旧 Manifest 签发失败 | PU,DC | S24,S42 |
| A03 | 有效 P/A，尚未 START | START/revoke 竞争 | 按提交顺序；无晚越权 START | PU,DC | S01,S43,S45 |
| A04 | 缓存仍标 VALID，实际已过期 | Start/eligibility | AUTH_EXPIRED，与后台 job 无关 | PU,E2E | S42,S45 |
| A05 | P7 已通过 A1 开始 | 签 A2 并 RESUME | 原 START 保留 A1，新 binding 引 A2 | PU,DC | S42,S45 |
| A06 | hold 有效，模型不可用 | fallback 选择 | 同样受限，无适用项则 UNAVAILABLE | PU,E2E | S05,S18,S42 |
| A07 | 普通规划队列和预算耗尽 | STOP 请求 | 独立容量处理撤销 | WF,E2E | S17,S01,S43 |
| A08 | 用户在无有效 A 时实际训练 | ingest actual | 保存事实，无虚构 execution binding | PU,E2E | S14,S44,S45 |
| W01 | 已 RESERVED 或 DISPATCH_INTENT | 各边界 kill worker | 仅许可前可退款，可能发送后 UNKNOWN 占用 | PU,WF | S27,S31,S32 |
| W02 | RESERVED，有取消与发送请求 | 两事务交错 | 取消释放与发送许可不能同时成立 | PU,DC | S31,S32,S27 |
| W03 | provider 返回 transient error | SDK/runtime retry | 每次物理请求有独立预算覆盖 | WF,E2E | S31,S32 |
| W04 | rev1=70min/full gym 正在运行 | rev2=20min/no equipment | rev1 失权，根预算/deadline 未重置 | PU,DC,E2E | S27,S28,S29 |
| W05 | token7 worker 暂停，lease 到期 | token8 接管，7 晚提交 | 7 不可提交；可信回执仅可结算 | PU,DC,WF | S27,S29,S32,S42 |
| W06 | intent 已取消或 deadline 结束 | 模型晚返回 | 不复活 intent/attempt，不新签 A | PU,WF | S27,S29,S42 |
| W07 | F1/D1/N1 已存在 | 修复出 F2 | D1/N1 不能用于 F2，重算计原预算 | PU,E2E | S34,S35,S37 |
| W08 | T6 已成功 commit | ACK 丢失后重发 | 返回相同 result/issuance，不重复写 | DC,WF,E2E | S02,S39,S42 |
| W09 | 两次搜索失败，无形式冲突证明 | workflow 结束 | 非 PROVEN_CONSTRAINT_CONFLICT | PU | S27,S37 |
| R01 | 九月更正八月事实 | cutoff=八月 replay | 排除九月获知修订 | PU,E2E | S14,S46,S47 |
| R02 | 相同 cutoff，历史/当前 release 不同 | 两模式 replay | 分别绑定指定 artifact bundle | PU | S46,S48 |
| R03 | 九月人工建立个体映射 | 八月 current backtest | 不导入未来个体知识 | PU,E2E | S20,S46,S47 |
| R04 | replay 产生模拟有效结果 | 尝试生产提交 | 角色/存储隔离拒绝，无 live issuance | DC,E2E | S46,S47,S42 |

四组交错 PU 可在 DDL 前用内存状态模型穷举；DC/WF 必须在后续实际数据库/worker 上运行。内存测试通过不能替代 PostgreSQL 行锁、唯一性冲突与进程故障验证。

## 8. V1 最小安全配置与存储成本边界

### 8.1 配置起点：`v1-local-shadow-deny-by-default`

这是可实现的默认配置定义，不是已经安装到服务的配置；不声称它可以提供自动处方。

| 配置 | 初始值/语义 | 放开条件 |
|---|---|---|
| 模式 | LOCAL_SHADOW；production issuance disabled | 协议与 auto-activation gate 通过 |
| Evidence 接收 | 可保存；来源明确；不默认获准 progression/sequence/nutrition | 对应用途 admission policy 已审核 |
| 进阶/序列/营养调整 | 未配置义务或 envelope 时 DENY，不猜默认值 | scope policy + resolver + fixtures 完成 |
| Durable auto approval | DISABLED；显式用户确认专用入口 | 独立 change-class policy 与 P1 release evidence |
| Protective controls | 专用 STOP/risk入口；pending hold 不自动过期解除 | 明确 clearance policy 才可解除 |
| Fallback catalog | 空；无适用项为 UNAVAILABLE | 每个模板具有完整 applicability/prohibited predicates |
| Offline START | DISABLED | 定义离线授权窗口、失效风险与产品策略后另行放开 |
| 模型/工具预算 | 缺任一必需限制则不启动；测试值由 fixture 显式给定 | 由评测/成本决定数值并发布完整 policy bundle |
| Replay | 可读获准历史、只写隔离 evaluation | 无生产写权限升级路径 |

测试 fixture 可以使用人工测试授权政策进入 T6/T7 的模拟环境，必须明确 test-only，并且不能误装为生产发行配置。静态配置存在不代表“缺配置时禁用”的运行代码已经验证。

### 8.2 Factset 与快照规模

S15/S16 采用 FULL checkpoint + DELTA 的有界链：DELTA 只记录 logical member 的 SET/REMOVE；解析按固定顺序覆盖至最近 FULL。policy 配置最大链深度，超限则构建新 FULL；未封存的链不发布。删除成员不删除历史事实。

Factset 不只包含成功准入事实，还要保留 resolver 所需的 UNRESOLVED/反证/admission 决策，否则会在物化阶段提前 cherry-pick。当前使用资格是各 scope 的决定，不是把所有未成功 evidence 从历史删除。

封存摘要对重建后的集合内容计算，重建/压缩发生在事务外；CompleteFactset 关闭写入并固定结果，T2-SEAL/T3 只核对 captured frontier 和完成结果，不再全量算 hash。规模过大时采用不可变成员块/分区属于物理优化，必须保持原子封存、cutoff 与 FK/完整性验证，不能先切 current pointer 再补成员。

Mandatory context 是有界的结构化摘要；完整 provider payload 与工具原始大结果用 blob ref，不在每个 snapshot 复制终身历史。后续深查仍绑定不可变修订/knowledge boundary。

### 8.3 查询与容量

- 当前授权查询读取 S01、S18、S42/S43、S49/S50/S51 与 session/head；制品闭包有界，撤销按 artifact identity 查询。S18 是同步维护、可验证的投影。全局共享 gate 的尾延迟与撤销优先待压测。
- revoke 用 epoch 屏障使旧签发失权，不在安全事务里更新用户所有旧 authorization rows。
- 原始 telemetry T1 与决策 T2 分开，避免每个 sample 锁 S01；输入准入/物化按源批次与 policy 分类。
- Reaper、outbox 和用户最近事实使用针对性索引；不默认给所有 JSON payload 建全字段 GIN。
- 先测试锁持有时间、热点用户写率、factset delta 重建、ledger write amplification 与历史存储增长，再决定分区/归档。逻辑设计本身不是百万 DAU 容量证明。

## 9. 本轮 protocol review 与未决事项

### 9.1 无需改变协议的逻辑决定

- Program 与 daily bundle 的当前真相采用单一 head pointer；历史内容保持不可变。
- 控制状态采用 append-only control_events + 同事务更新的 control_heads；不依赖异步撤销。
- AuthorizationIssuance 与事件、执行绑定分离；不恢复 A1，不因 A2 重写 START。
- 预算采用 ledger 历史 + reservation/intent 同事务余额，UNKNOWN 占用与 confirmed actual charge 分开。
- manifest/tool 查询使用 input revision，所有动作提交再查当前 epoch/request/fence。

### 9.2 冻结前必须确认的实施语义

| 项目 | 本设计提出的精确定义 | 验证要求 |
|---|---|---|
| 幂等 dispatch | 仅首次 permit transition winner 能发送；重放 receipt 不再次发送 | W01/W02/W03 的 executable state model + worker test |
| 时效线性化 | 持锁后的 guard acceptance time 记录；后续响应不能把已过期资格呈现为当前有效 | A03/A04 与锁等待跨 deadline fixture |
| Revocation / risk ACK | raw received 与 protective action applied 是不同响应语义；安全 ACK 要等 T2 | E02/A01/A07 的 API/E2E |
| 当前指针与重建 | active head/cache 是同步投影，必须可验证；失配 fail closed | DC：绕过 writer 的尝试被拒，重建不短暂放行 |
| 暴露对账 | 实际执行替换同一 session 对应计划暴露，不重复相加；部分执行保留 remaining/unknown | 执行域 fixture + Policy Envelope 契约 |

这五项已有部分抽象模型验证；交错仅覆盖报告列出的有限场景，完整暴露对账、真实数据库锁与 worker 故障尚未验证。若测试迫使改变授权含义或原子边界，先修订 Candidate，再变更本设计；不能以迁移脚本偷偷修补协议。

字段名、索引顺序、分区、数值 TTL 与已定义政策阈值可在不减弱上述含义的前提下后续调整。FK 可延迟性、不可变写权限/trigger、隔离级别和时间函数选择属于 DDL/事务实现审查项目，不在本文件中冒充已经落地。

### 9.3 下一阶段交付边界

1. 已交付 pre-freeze model/fixtures/report；先评审本轮新权限与事务边界，不把模型 PASS 当作协议自动冻结。
2. 冻结前完成相关 protocol review 与完整 policy 配置；本文件的 shadow 配置不能替代 auto-activation 配置。
3. 协议 FROZEN 后生成 PostgreSQL DDL、typed command contracts 与 repository transaction interfaces。
4. 在真实 PostgreSQL 上运行 DC/WF/E2E，再构建 local vertical slice、AI Fitness Planner、shadow mode；通过 gate 后才签发生产执行授权。

## 10. 本文件验证范围

配套 v0.2 traceability 验证 51 个逻辑关系、18 条 invariant、T1–T8 和原 34 个验收 ID；model report 单独记录模型结果。新增 18 个边界模型测试不替换原验收。未建立 PostgreSQL 表、未执行真实 worker 故障、未验证线上容量。Protocol 仍为 Freeze Candidate。

## 11. r2 新命令与错误合同

以下是旧 §3 的补充；完整命令入口仍由原所有者负责。模型方法是服务内部原型，不等同于完成 typed API 契约。

| 命令 | 唯一所有者 / 原子边界 | 幂等身份 / 重放 | 拒绝码 |
|---|---|---|---|
| BeginBuild / WriteCandidate | CanonicalViewService，build-only | build command key / member operation key + expected member revision；同 key 异 payload 拒绝 | BUILD_CLOSED、IDEMPOTENCY_CONFLICT |
| CompleteFactset | CanonicalViewService，build 写屏障 | build_id + closed_member_revision + completion digest；相同完成凭据返回原 READY/SEALED | MEMBERS_NOT_SUPPORTED、BUILD_CHANGED |
| SealFactset | CanonicalViewService / T2-SEAL | build_id + completion identity；重放只返回旧封存结果，不能重切 head | FACTSET_NOT_READY、BUILD_STALE、BUILD_CHANGED |
| RegisterArtifact | SafetyRegistry / registry exclusive | immutable artifact identity/hash；已有不同内容拒绝，不覆盖 | IMMUTABLE_ARTIFACT、ARTIFACT_UNKNOWN、VALIDITY_UNDEFINED |
| RevokeArtifact | SafetyRegistry / T2-GLOBAL | authenticated management actor + command key + artifact/payload hash；同 key 同 hash 返回原撤销 | COMMAND_NOT_AUTHORIZED、ARTIFACT_UNKNOWN、IDEMPOTENCY_CONFLICT |
| Commit/Issue | AuthorizationService / T6 | 原 commit identity；旧结果重放只表示历史结果，另查当前资格 | ARTIFACT_REVOKED、ARTIFACT_EXPIRED、REGISTRY_UNAVAILABLE、VALIDITY_UNDEFINED、DEPENDENCY_EXPIRED，及原 guard 码 |
| START/RESUME/CONTINUE | ExecutionService / T7 | session/action key + exact P/A；历史回执不作为新执行许可 | 上述 registry/validity 码 + AUTH_EXPIRED、EPOCH_MISMATCH、AUTH_REVOKED |

Registry 故障/管理员身份与通用幂等 gateway 仍是生产适配器义务；模型只实现选定命令的回执和相关边界，不冒充所有 API contract 已完成。

## 12. 依赖有效期与审计落点

S42 保存完整 validity certificate；S24/S21/S36 和 S49 的期限均有身份对应。授权有效期取所有关键依赖结束、政策 TTL、请求上限及 calendar/session boundary 的最小值。TIMELESS 必须指向显式批准政策和理由；缺失值拒绝。证据/admission freshness 必须由 resolver 的最早到期或明确成员期限传递，不能只保存查询完成时间。

执行检查同时读取用户失效屏障与当前 registry。普通新 Manifest 与无关 artifact revoke 不影响旧 A；依据撤回由 T2-IN 同步 epoch 捕获，制品撤销由 T2-GLOBAL 捕获，到期直接由时间判断。S42 历史保持不可变。
