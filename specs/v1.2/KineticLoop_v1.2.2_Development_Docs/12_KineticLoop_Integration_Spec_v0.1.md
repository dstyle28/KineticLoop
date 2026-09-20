# KineticLoop — Integration & Data Source Specification v0.1

状态：**Development Contract / Provider Integration Baseline**  
文档版本：v0.1  
产品文档集：KineticLoop v1.2.2 Development Docs  
上位约束：`DOC-PROTOCOL-V1.2`、`DOC-DB-V0.2`。本文件不得弱化 Evidence Admission、Decision Publication、Authorization、Planning Workflow 或 Replay 的冻结语义。

> 核心原则：**Provider transport is evidence transport, not canonical truth.** 外部平台负责提供观测或 provider-derived estimates；KineticLoop 负责 source identity、版本、关联、admission、canonical fact、projection 与 action authorization。

## 0. 为什么这份 Spec 是开发前置条件

Integration 决定两个产品问题：

1. **KineticLoop 实际能看到什么数据？**
2. **某个数据源缺失或延迟时，产品还能做到什么？**

因此任何“readiness、progression、fatigue、nutrition、weight trend”功能都不能只写算法而不写数据来源与缺失语义。

本规范截至 **2026-09-18** 对官方公开文档做过能力核验；provider API、商业条款和平台权限后续变化时必须重新审查。

---

## 1. V1 数据源结论

| Source | V1 角色 | 产品依赖级别 | 缺失时退化行为 | 当前可用性判断 |
|---|---|---:|---|---|
| Authenticated manual/chat | 主观状态、纠正、fallback workout reporting、命令入口 | REQUIRED_BASELINE | 无替代时只能使用其他 provider facts；关键歧义保持 unresolved | 可直接实现 |
| Hevy Public API | **Strength actuals 主来源**：workout、exercise、sets/reps/load、exercise identity；可辅以 body measurement | LAUNCH_SCOPE_TARGET | 退化到 manual/chat actuals；禁止从 HealthKit strength label 补全 set 细节 | 技术可用；API 仍标 early/unstable，且当前仅 Hevy Pro |
| Apple HealthKit | **iOS passive health/activity hub**：sleep、HR/HRV/RHR、workout/cardio、steps/energy、weight、可能的 nutrition 等 | LAUNCH_SCOPE_TARGET | readiness/data completeness 变 PARTIAL/UNKNOWN；仍可凭训练历史+主观状态规划 | 技术可用；必须有 iOS bridge；read permission 存在隐私性不可判定语义 |
| Oura Cloud API / MCP | 高价值 sleep/recovery/activity source；可增加 same-source recovery context | CONDITIONAL / NON-BLOCKING | 使用 HealthKit/主观状态并降低 readiness completeness；不得复制旧 Oura 值当 current | 技术上可用；进入 AI 路径前须完成 Oura 当前 Agreement/consent/retention 合规 gate |
| Nutrition via HealthKit | calories/macros 等 nutrition samples（取决于上游 app 是否写入） | OPTIONAL_SOURCE | manual/import/provider-specific source | HealthKit 支持 nutrition types，但不能假设某特定 nutrition app 一定写入全部字段 |
| MacroFactor export | expenditure、weight trend、scale weight、calories/macros/targets 的批量/周期导入候选 | OPTIONAL_IMPORT | 其他 nutrition/weight source | 官方支持 Granular/Quick Export；不假设公开实时 REST API |
| DEXA / body-composition file | 低频 body-composition report | OPTIONAL_IMPORT | 无 body-comp 结论，只使用 weight/measurement trend | 文件解析 + evidence admission |

### 1.1 Launch recommendation

**推荐 V1 launch-source scope：**

```text
Required product fallback:
- authenticated manual/chat

Launch-scope target integrations:
- Hevy
- Apple HealthKit bridge

Non-blocking / conditional:
- Oura
- nutrition provider imports / MacroFactor export
- DEXA/body-composition files
```

这里的 `NON-BLOCKING` 不等于“不重要”。Oura 对 recovery context 很有价值，但 KineticLoop **必须能够在没有 Oura 的情况下正确降级运行**，否则 provider 合规、授权或 outage 会直接让 planner 失效。

---

## 2. Canonical ingestion flow

所有外部来源统一经过：

```text
Provider / User Input
      ↓
Source Adapter / Authenticated Command Surface
      ↓
EvidenceRevision
      ↓
CandidateAssertion / Event Association
      ↓
Action-scoped Admission
      ↓
CanonicalFactRevision
      ↓
Factset / Projection
      ↓
DecisionManifest
      ↓
AI reasoning + Action Authorization
```

### 2.1 禁止的旁路

```text
Hevy → progression pointer                     ❌
HealthKit → readiness verdict                  ❌
Oura readiness score → FORCE_REST             ❌
Wearable strength workout → invented sets     ❌
Nutrition app calorie target → active Program ❌
Provider free text → user approval             ❌
```

Provider 数据永远没有 command authority。

---

## 3. Domain ownership / source responsibility

### 3.1 Strength training

**Preferred evidence:** Hevy structured workout/set data → authenticated user correction/report → other provider event evidence.

HealthKit `HKWorkout` 可以证明发生过一项 workout，并提供/关联 duration、distance、energy、heart-rate 等客观信息，但 **MUST NOT** 用 workout activity label 推导：

- exercise name；
- set count；
- reps；
- load；
- RPE/RIR；
- blueprint completion。

如果 Hevy 与 chat 是同一次 workout，必须映射到同一 `underlying_event_identity`，而不是算两次训练。

### 3.2 Cardio

可来自：

- HealthKit workout + associated heart-rate/distance/energy samples；
- Oura workout summary（若启用）；
- Hevy（若用户在那里记录 cardio）；
- manual report。

Cardio modality/time/distance/HR 可以被接受为 objective execution facts，具体资格仍按 source、coverage、correction 和 association policy 判断。

### 3.3 Sleep / recovery

可来自 HealthKit、Oura 与主观状态。

关键规则：

- 同一 metric 的 baseline SHOULD 保持 same-source；不能把 Oura HRV baseline 与 Apple Watch HRV 当作天然可交换序列。
- Oura/Apple 提供的 provider-derived score/estimate 保留其来源语义；KineticLoop readiness 是独立 projection。
- 任何 source 缺失都必须反映到 coverage/completeness，不可用昨日值伪装今天值。

### 3.4 Body weight / measurements

可能来源：HealthKit body-mass sample、Hevy body measurement、manual input、nutrition-app/export。

多来源相同测量需做 event association；不要简单使用“优先级覆盖”。source lineage、时间、设备和修订都保留。

### 3.5 Nutrition

可能来源：

- HealthKit dietary types；
- provider-specific export/import；
- manual intake；
- future direct provider integration。

**KineticLoop 不假设 MacroFactor expenditure 通过 HealthKit 可获得。** MacroFactor 当前官方公开能力可作为 export import source；provider-specific derived expenditure 必须保留 `PROVIDER_DERIVED_ESTIMATE` 性质。

### 3.6 Subjective / commands

Energy、soreness、pain、schedule、equipment availability 等来自 authenticated user surface。

但是：

```text
Authenticated user content != Authorized command
```

STOP、FORCE_REST、durable approval 等必须通过冻结协议定义的 command capability/confirmation flow。

---

## 4. Hevy integration contract

### 4.1 Current official capability

Hevy 的 Public API 当前提供 workouts、workout events、exercise templates、exercise history、body measurements 等。`/v1/workouts/events` 用于获取自指定时间以来的 workout update/delete events；官方同时明确 API 仍处于早期、结构可能变化，当前仅对 Hevy Pro 用户开放。

### 4.2 KineticLoop use

Hevy 是 V1 strength actual capture 的首选 provider：

```text
Hevy Workout
  → EvidenceRevision(provider=HEVY, provider_workout_id)
  → source exercises / source sets
  → exercise mapping
  → canonical actual workout/set revisions
```

### 4.3 Sync strategy

V1 不假设 webhook。

```text
Initial backfill:
GET workouts / pagination
GET exercise templates

Incremental:
GET workout events since last provider watermark
  → fetch updated workout detail as required
  → process delete/update

Periodic reconciliation:
compare recent-window provider state against local source identities
```

Polling schedule必须 jitter；精确频率由 policy/config 决定，而不是协议常量。

### 4.4 Identity and correction

必须保留：

- provider workout ID；
- provider exercise template ID；
- provider updated/deleted event identity or retrievable revision context；
- received/known time；
- raw payload hash；
- canonical mapping version。

Hevy workout 更新/删除必须形成 evidence revision/correction，不做 destructive overwrite。

### 4.5 Exercise mapping

```text
Hevy exerciseTemplateId
→ source_exercise_identity
→ mapping decision
→ canonical exercise identity
→ blueprint-role compatibility
```

UNKNOWN/AMBIGUOUS mapping：

- 仍可保存 actual event、load/reps 等已知事实；
- 不允许自动宣称满足某 blueprint role；
- AI 可提出 mapping candidate，但 approval/admission 决定永久语义。

### 4.6 Hevy go/no-go

**GO for V1 adapter development**, with two explicit risks：

1. API 官方自称可能变化，因此 adapter 必须 isolation + contract tests；
2. Hevy Pro requirement 影响用户可用范围，不能作为唯一 workout-report channel。

---

## 5. Apple HealthKit integration contract

### 5.1 Architecture

HealthKit 是设备本地 store，因此需要 iOS bridge：

```text
iPhone / Apple Watch / third-party apps
        ↓
      HealthKit
        ↓
KineticLoop iOS Health Bridge
        ↓ authenticated batch/upload
Backend EvidenceService
```

Backend 不能直接远程查询用户 HealthKit store。

### 5.2 Incremental collection

推荐：

- `HKObserverQuery` / background delivery：通知“有变化”；
- `HKAnchoredObjectQuery`：使用 anchor 拉取自上次之后新增和 deleted objects；
- 持久化每个 sample type/query scope 的 anchor；
- 每个上传 batch 保留 bridge/device/app version、source revision 和 data cutoff。

Apple 文档明确 anchored query 支持返回新增与删除对象；observer query 只通知发生变化，通常需要再执行 anchored/sample query 才能取得实际数据。Background delivery 必须在真机测试，Simulator 不支持相同的后台 server-query 行为。

### 5.3 Identity / provenance

每个 HealthKit object 至少采集：

- HealthKit UUID；
- sample type；
- start/end；
- value/unit 或 category；
- `sourceRevision`；
- `device`（如果可用）；
- metadata 中允许且必要的字段；
- bridge upload identity；
- deletion event。

`sourceRevision` 标识保存该对象的 app/device及版本信息，因此不能把所有 HealthKit 数据笼统当作“Apple 测量”。

### 5.4 Permission semantics — critical

HealthKit read permission 有特殊隐私语义：app **不能可靠地区分“用户拒绝读取”与“该类型确实没有数据”**；limited history access 是能明确识别的一类状态。

因此 KineticLoop MUST NOT：

```text
query returns no samples
→ metric = zero                 ❌
→ user did not sleep            ❌
→ no historical HRV exists      ❌
→ coverage COMPLETE             ❌
```

Bridge 必须输出 coverage metadata，例如：

```text
REQUESTED
LIMITED_FROM(date)
OBSERVED_SAMPLES_PRESENT
NO_VISIBLE_SAMPLES_UNKNOWN_CAUSE
```

而不是虚构 READ_DENIED / FULL_GRANTED 状态。

### 5.5 V1 read-type groups

最终 exact type list 在 iOS contract 实现时冻结；V1 目标域：

**Recovery / sleep**
- sleep analysis
- heart rate
- resting heart rate
- HRV SDNN
- respiratory rate
- wrist/body temperature only if product policy explicitly uses it

**Activity / cardio**
- workouts
- heart rate associated around workout windows
- active energy
- walking/running/cycling distance as applicable
- steps / activity summaries if required by program target logic

**Body**
- body mass
- body fat / related body measurements only if explicitly supported and meaningful

**Nutrition (optional)**
- dietary energy consumed
- protein
- carbohydrate
- total fat

The availability of a HealthKit type does not mean any upstream app actually writes useful/current data for it.

### 5.6 Sleep aggregation

Sleep total must use explicit category semantics; KineticLoop policy determines accepted asleep categories and MUST exclude awake/in-bed from actual sleep total unless a specific metric says otherwise. Ambiguous or overlapping source samples require reconciliation, not naive duration sum.

### 5.7 HealthKit go/no-go

**GO and recommended launch-scope target.**

Main risks：permission ambiguity, multi-source duplicate samples, late replacement/deletion, device-only background testing. These are engineering/data-quality risks, not blockers to adapter development.

---

## 6. Oura integration contract

### 6.1 Current official capability

Oura Cloud API uses OAuth2 and currently exposes scopes including `personal`, `daily`, `heartrate`, `workout`, `tag`, `session`, `spo2` (plus email). `daily` covers daily sleep/activity/readiness summaries. Current public docs report a 5,000 requests / 5-minute API rate limit, and public API applications default to a ten-user limit until wider application approval.

### 6.2 Product value

Useful Oura evidence includes:

- sleep timing/duration/provider sleep metrics；
- daily readiness/activity/sleep summaries；
- heart-rate series where available；
- workouts；
- SpO2 summary if product use is justified；
- sessions/tags only if explicitly needed。

KineticLoop must not use Oura's `readiness` value as its own readiness verdict. It is an input/provider-derived summary.

### 6.3 API/MCP and AI boundary

Current Oura API/MCP Agreement is effective **June 8, 2026** and expressly governs use of Oura User Data with APIs/MCP and third-party AI technology. The agreement permits certain processing in connection with AI subject to its conditions, consent and protective obligations; this spec **does not make a legal conclusion that any specific KineticLoop pipeline is compliant**.

Therefore Oura has a mandatory deployment gate:

```text
OURA_DISABLED_FOR_AI
until:
- approved integration lane documented
- consent scopes documented
- retention/deletion behavior documented
- third-party AI/data-processing terms reviewed
- exact fields allowed into model context documented
```

Possible implementation lanes are kept separate:

**Lane A — Oura API → deterministic backend evidence**
- raw/provider-derived data retained and processed according to approved policy；
- AI exposure only if compliance gate explicitly allows selected abstractions/fields。

**Lane B — Oura MCP**
- orchestrator-controlled retrieval when approved；
- still transformed into immutable context/evidence records；
- Agent does not own mutable canonical state。

Do not assume that turning raw data into a local derived feature automatically eliminates contractual restrictions.

### 6.4 Sync

No KineticLoop design assumes webhook availability. V1 adapter should support:

- OAuth2 token lifecycle；
- date/cursor-style polling appropriate to endpoint；
- source watermarks per stream；
- backfill and late-data reconciliation；
- rate-limit handling；
- scope revocation / partial-scope behavior。

### 6.5 Oura go/no-go

- **GO for prototype/deterministic adapter work** after normal credential handling is available.
- **NO-GO for feeding Oura-derived data into production AI planning** until compliance gate is approved.
- **Not a V1 launch blocker**: planner must operate with Oura absent and mark readiness coverage accordingly.

---

## 7. Nutrition and body-composition auxiliary integrations

### 7.1 HealthKit nutrition

HealthKit defines nutrition data types including dietary energy and macronutrients. Treat each sample with source identity; do not assume complete daily intake just because the type is requested.

### 7.2 MacroFactor

Current official MacroFactor help documents provide:

- Granular Export；
- Quick Export including expenditure, weight trend, scale weight, calories, macros and primary nutrition targets。

V1 may support file/export ingestion. **Do not architect against an assumed public real-time REST API unless one is officially documented when implementation begins.**

MacroFactor expenditure / weight trend is a provider-derived estimate and must retain that semantic class.

### 7.3 DEXA/body composition

Treat uploaded report as immutable source evidence. Extraction produces candidate assertions with page/span provenance. Numeric range validation alone does not make extracted fields authoritative; key measurements require appropriate admission/confirmation rules.

---

## 8. Cross-source reconciliation

### 8.1 Never merge by field name alone

The following do not necessarily represent the same thing:

```text
Oura HRV
Apple HealthKit HRV SDNN
another app's imported HRV
```

Canonical observation identity includes measurement definition, source lineage and method.

### 8.2 Underlying event association

For workouts/body measurements:

```text
Hevy workout W1
HealthKit workout H1
user report C1
```

can resolve to one underlying event E1.

Source count = 3.  
Independent workout count = 1.

Association may remain AMBIGUOUS when timestamps/duration/content do not provide adequate evidence.

### 8.3 Source conflict

Conflict is preserved. No universal hierarchy silently overwrites another provider. Domain-specific policy determines which evidence is eligible for which action.

Examples:

- Hevy exact load/reps vs HealthKit workout label → Hevy can support strength-set facts; HealthKit cannot contradict missing set detail because it never supplied it.
- Two body-weight samples five minutes apart from different apps may be duplicates or separate measurements; event association decides.
- User explicit correction may supersede an extracted assertion but remains USER_REPORTED evidence provenance.

---

## 9. Freshness, completeness, and data-lateness contract

Every provider stream exposes a source status:

```text
connection_status
last_success_at
last_attempt_at
source_watermark
coverage_start / coverage_end
freshness
completeness
partial_scope / permission ambiguity
last_error
```

Provider-specific watermark is not a universal clock.

Daily planning receives a `DailyInputStatus` summary such as:

```text
HEVY_STRENGTH: COMPLETE_THROUGH(...)
HEALTHKIT_SLEEP: PARTIAL / NO_VISIBLE_SAMPLES_UNKNOWN_CAUSE
HEALTHKIT_HR: FRESH
OURA_DAILY: UNAVAILABLE_PROVIDER_DISABLED
NUTRITION: PARTIAL
```

Planning may proceed with PARTIAL/UNKNOWN if policy permits; it must not substitute stale values as current facts.

---

## 10. AI context exposure policy

Source ingestion and AI context are two separate permissions.

| Data class | Canonical storage | Default AI context |
|---|---|---|
| Hevy structured strength actuals | Yes | Allowed through canonical normalized facts |
| HealthKit normalized sleep/HR/activity facts | Yes, with consent | Allowed through context tools/policy |
| HealthKit raw metadata/free text | Minimal/controlled | No unless specifically needed |
| Oura raw/provider data | Only under approved retention policy | Denied until Oura AI/compliance gate |
| Provider free text/notes | Evidence, low trust | Untrusted content; never command authority |
| Uploaded report raw text | Controlled evidence/blob | Only relevant spans/accepted facts by policy |

AI may request deeper history through read-only context tools, but tools return source/freshness/coverage and never elevate provider text into command authority.

---

## 11. Common ProviderAdapter interface

Conceptual Python contract:

```python
class ProviderAdapter(Protocol):
    provider: ProviderId

    async def connection_status(...) -> ConnectionStatus: ...
    async def initial_backfill(...) -> BackfillResult: ...
    async def fetch_incremental(cursor: ProviderCursor | None, ...) -> ProviderBatch: ...
    async def reconcile(window: TimeWindow, ...) -> ReconciliationResult: ...
    async def normalize(batch: ProviderBatch, ...) -> list[EvidenceEnvelope]: ...
```

`EvidenceEnvelope` must carry:

```text
subject binding
provider/source connection
provider object identity
provider revision / observation key
observed/effective time
received/known time assigned by server
payload hash/blob ref
source class / trust class
lineage
schema/adapter version
```

Adapters **do not** call progression, readiness, sequence or prescription services directly.

---

## 12. Provider connection lifecycle

```text
UNCONFIGURED
  → AUTH_REQUIRED
  → CONNECTED
  → DEGRADED
  → REAUTH_REQUIRED
  → DISABLED
```

`CONNECTED` only describes transport/auth health; it does **not** mean a specific metric has complete coverage.

Disconnect/revoke events do not delete canonical historical evidence automatically; retention/deletion follows source-specific consent/privacy policy.

---

## 13. V1 implementation work packages

### INT-01 — Integration contract registry

- Provider IDs, source classes, stream IDs, watermark types
- common adapter interface
- connection status contract
- evidence envelope contract

### INT-02 — Hevy adapter

- auth/config
- exercise-template sync
- workout backfill
- workout events incremental sync
- update/delete correction
- mapping queue
- contract fixtures

### INT-03 — HealthKit iOS bridge

- permissions UX
- observer/anchored query engine
- per-type anchors
- delete handling
- sourceRevision/device capture
- bridge batch upload + retry/idempotency
- device background-delivery tests

### INT-04 — Cross-source workout reconciliation

- Hevy ↔ HealthKit ↔ manual underlying-event association
- duplicate and ambiguity tests

### INT-05 — Oura deterministic adapter

- OAuth/scopes
- stream watermarks
- API backfill/polling
- scope/rate-limit handling
- **AI context disabled by default**

### INT-06 — Oura compliance/AI gate

- legal/product review artifact
- consent/retention rules
- third-party AI exposure decision
- field-level allow/deny policy
- tests proving denied Oura data cannot enter AI context before gate

### INT-07 — Nutrition/body import adapters

- HealthKit nutrition
- MacroFactor export import
- DEXA report ingestion

---

## 14. Integration release gates

No provider adapter is `LAUNCH_READY` until all applicable gates pass:

1. identity/idempotency test；
2. update/delete/correction test；
3. late/out-of-order delivery test；
4. partial permission/scope test；
5. provider outage/retry/backoff test；
6. data-source provenance preserved through canonical fact；
7. duplicate underlying event does not double count；
8. unauthorized/unapproved data cannot enter AI context；
9. adapter disable does not block STOP/control path；
10. source absence produces PARTIAL/UNKNOWN, not synthetic zero/current values。

### 14.1 Product usability gate

The system is considered **usable without a specific optional provider** only if its documented degradation path has an E2E test.

Examples:

```text
No Oura → plan can still be produced from HealthKit + training history + subjective inputs, with reduced readiness coverage.
No Hevy → manual workout ingestion still works; no strength sets are invented from HealthKit.
No HealthKit → planner can operate in partial-data mode using training history + manual recovery check-in, if policy allows.
```

---

## 15. Provider decision table

| Provider | Adapter Dev | AI Planning Use | Production Launch Dependency | Decision |
|---|---:|---:|---:|---|
| Manual/chat | YES | YES after admission | baseline | BUILD |
| Hevy | YES | normalized canonical facts | target | BUILD |
| HealthKit | YES | normalized canonical facts | target | BUILD |
| Oura | YES deterministic lane | **GATED** | non-blocking | BUILD ADAPTER / HOLD AI EXPOSURE |
| MacroFactor export | YES later | normalized imported facts/estimates | non-blocking | OPTIONAL |
| DEXA | YES later | admitted report facts | non-blocking | OPTIONAL |

---

## 16. Open implementation decisions

These are configuration/engineering decisions, not permission-semantic changes:

- exact Hevy polling cadence and recent-window reconciliation length；
- exact HealthKit V1 requested sample types；
- HealthKit bridge batch size/retry window；
- Oura endpoint polling cadence and whether MCP is used at all；
- nutrition launch source；
- data retention periods per provider；
- source-specific backfill horizons；
- whether Hevy body measurements are enabled when HealthKit body mass is also present。

If any decision changes evidence authority, command authority, authorization semantics or T1–T8 transaction boundaries, it requires protocol/ADR review rather than being treated as adapter configuration.

---

## 17. Official capability references verified 2026-09-18

- Hevy Public API Docs: https://api.hevyapp.com/docs/
- Apple HealthKit `HKAnchoredObjectQuery`: https://developer.apple.com/documentation/healthkit/hkanchoredobjectquery
- Apple HealthKit observer/background query guidance: https://developer.apple.com/documentation/healthkit/executing-observer-queries
- Apple HealthKit authorization/read-privacy behavior: https://developer.apple.com/documentation/healthkit/authorizing-access-to-health-data
- Apple HealthKit data types: https://developer.apple.com/documentation/healthkit/data-types
- Apple HealthKit `sourceRevision`: https://developer.apple.com/documentation/healthkit/hkobject/sourcerevision
- Oura API authentication/scopes: https://cloud.ouraring.com/docs/authentication
- Oura API error/rate-limit docs: https://cloud.ouraring.com/docs/error-handling
- Oura API and MCP Agreement, effective 2026-06-08: https://cloud.ouraring.com/legal/api-agreement
- MacroFactor data export: https://help.macrofactorapp.com/en/articles/68-export-your-data
