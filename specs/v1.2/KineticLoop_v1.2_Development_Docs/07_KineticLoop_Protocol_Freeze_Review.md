# KineticLoop v1.2 — Protocol Freeze Review

状态：**APPROVED / FROZEN**  
冻结对象：`KineticLoop_v1.2_Protocol_FROZEN.md` 与其下游 `KineticLoop_DB_Schema_Design_v0.2_FROZEN.md`。  
实现状态：**NOT STARTED**。无 PostgreSQL DDL、无生产服务、无真实 provider/LLM 链路、无 production auto-activation。

## 1. Freeze 决议

Protocol v1.2 正式冻结。冻结的是协议语义，不是生产实现成熟度。Evidence Admission、Decision Publication、Authorization、Persistent Bounded Planning Workflow、Replay 五个协议，以及 18 条 invariant、T1–T8 原子边界、SafetyRegistry、Factset build→seal、budget reservation ledger 和 Authorization validity closure，成为开发基线。

默认环境保持 `LOCAL_SHADOW / deny-by-default`。自动授权、durable auto approval、fallback catalog、offline START 和未配置 progression/nutrition action 均继续关闭。

## 2. Freeze 前三个 P0 的关闭状态

| P0 | 冻结语义 | 有限模型证据 | 尚待真实实现验证 |
|---|---|---|---|
| Factset build→seal | BUILDING/READY 仅候选；SEALED 才是 canonical history；T2-SEAL 只核验并切 head | P01–P03 + seal/input interleaving | PostgreSQL 写屏障、FULL/DELTA 规模、清理与恢复 |
| 全局制品撤销 | SafetyRegistry 传递依赖 + T2-GLOBAL emergency revoke；publish/issue/start/continue 均检查；用户 STOP 不依赖 registry | artifact revoke vs issue/start/publish | 管理 capability、真实共享/排他 gate、公平性/负载、registry outage |
| 依赖有效期闭包 | Authorization 到期取所有关键依赖和 policy/calendar 上限的最小值；缺失 deny | dependency expiry vs START + boundary cases | 真实时钟/DST、完整 freshness policy、生产 TTL 数值 |

## 3. 最终补充：全局撤销时间语义

全局 artifact revoke 的执行失效线性化点是 **T2-GLOBAL 事务成功提交**。`recorded_at`/commit time 决定系统从何时拒绝依赖该 artifact 的新 publish / issue / START / RESUME / CONTINUE。`effective_at` 仅用于事故、业务和审计语义：

- backdated `effective_at` 不追溯改写过去已发生的授权/START；
- future `effective_at` 在 V1 不产生 scheduled revoke；
- 若未来支持计划撤销，必须定义新状态/协议，不能复用 emergency revoke。

## 4. 可执行模型证据

本 release 重新运行 `python3 protocol_model/run_model.py`，状态 PASS。冻结基线的有限模型结果为：

- 原 34 项 acceptance model case：34/34 PASS；
- 新增边界 case：18/18 PASS；
- 关键 interleaving scenario：9/9；
- 完整调度 589，访问前缀 2,997；
- 模型内 deadlock / invariant violation：0 / 0；
- seeded negative mutants：8/8 被检出；
- 真实 PostgreSQL / 真实进程故障 / live LLM：0 / 0 / 0。

这些结果证明的是**冻结协议的有限状态模型没有发现已编码反例**，不证明生产数据库隔离、网络恢复、授权 UX、训练/营养 policy 数值或医学安全。34 项 PU/DC/WF/E2E 仍保持 NOT_RUN。

## 5. Freeze change control

无需升级 protocol version 的变化：字段命名、物理分表、索引、分区、ORM、缓存、SQL 语法、非语义性错误文案、已明确为配置的 policy 数值。

必须升级 protocol version 或写明确 ADR + compatibility decision 的变化：任一 invariant、T1–T8 原子边界、Evidence admission 资格、Manifest 发布、Authorization/SafetyRegistry guard、Planning budget/lease/fencing、Replay knowledge boundary、command authority 或 failure terminal semantics。

## 6. 开发 gate

**可以开始开发：YES。**

开发必须从 DDL/typed contracts/真实 PostgreSQL concurrency tests 开始；AI Agent 接入晚于 canonical state、authorization evaluator 和 planning workflow 的最小实现。

**可以自动激活 production prescription：NO。** 自动激活仍需通过 frozen protocol 第 9 节 34 项验收、真实 DC/WF/E2E、完整 production policy bundle、授权审计、降级 UX 和 release evaluation。
