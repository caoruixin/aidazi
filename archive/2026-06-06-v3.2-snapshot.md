# aidazi Framework Plan — v3.2 archive (2026-06-06)

**Status**: 单文件冷启动归档。集成 v1 §A-§I + v2 settled answers + Δ-1~Δ-17 + 5 pushback open items + 4 alignment confirmations 全部内容。
**Source files**(可溯源):
- `/tmp/framework-plan-draft.md` — v1 §A-§I 完整骨架
- `/tmp/framework-plan-v3-delta.md` — Δ-1~Δ-8 + §L worked example
- `/tmp/framework-plan-v3-followup-delta.md` — Δ-10/Δ-12/Δ-13/Δ-14
- `/tmp/framework-plan-v3-deltas-15-16.md` — Δ-15 amendments + Δ-16 + Q3
- 本轮 inline embed — v2 charter / Δ-9 / Δ-11 / Δ-15 initial design / Δ-17 全文 / 5 pushbacks / 4 aligns

---

## §0 — Reading guide

本归档是 aidazi(独立 standalone repo)的设计快照。**aidazi 仓库尚未存在**,本文档是 aidazi 仓库 bootstrap 的冷启动输入。aidazi 一旦初始化,live 框架文档会逐项落地到 `aidazi/current/` `aidazi/process/` `aidazi/templates/` `aidazi/examples/csagent-reference/`;本归档则进入 `aidazi/archive/2026-06-06-v3.2-snapshot.md`。

读法:**新读者** 顺序读 §1 → §2 → §3 → §5 → §7,理解骨架后跳读 §9 中关心的 Δ。**已读过 v2/v3** 仅读 §9 Δ-15/Δ-16/Δ-17 增量 + §13 open items。**csagent / hermes / fortunes 三个 donor 永不反向迁移**(详 §6)。

---

## §1 — Charter

aidazi 是一个**纯文档**框架,定位为 AI Agent / Agentic Workflow / Demo App 三轨道项目从 0→1 立项到生产稳态的治理脚手架。**零运行时代码复用**。csagent / hermes / fortunes 是**捐献者**(donor),不是消费者;new domain agents 从零起步,以 aidazi templates + worked examples 为模板填空。`aidazi → donor` 反向同步**不存在**(donor 自身演化与 aidazi 解耦)。框架的本体是 (a) Constitution 治理 + (b) 5-role 协作模型 + (c) 模块模板(M-Evaluation light / M-Trace conditional / M-Autoloop conditional)+ (d) 处理流程文档 Layer B + (e) §L worked-example instance 镜像。

---

## §2 — Framework anatomy(Δ-1 + v1 §A)

### §2.1 三正交维度

**Dim 1 — Layer(静态)**:
- **A Constitution** 始终加载、≤20KB、永恒规则
- **B Process** 按需加载、按角色触发、协作机理
- **C State Ledgers** 周期 live、保留规则
- **D Prompt Artifacts** 单次会话自洽 prompt

**Dim 2 — Portability tier**(v1 提案,v3.2 落定):
- **T0 Universal** AI-agent + workflow + demo 通用(doc-tier 模型 / self-contained prompt invariant / role registry shape)
- **T1 App-type** 仅适用某轨道(Type A LLM-first / Type B SOP-row+verification / Type C four-phase demo)
- **T2 Domain** 某轨道内某领域(CS-FAQ / 仓储 / 物业 / 制造)
- **T3 Project** 某代码库实例化值(`<<PROJECT:>>` 填空)

**Dim 3 — Lifecycle**: static / reviewed / generated / append-only

### §2.2 Layer × Tier 矩阵(关键单元格)

| | T0 Universal | T1 App-type | T2 Domain | T3 Project |
|---|---|---|---|---|
| **A** | Iteration rule §1.5 / Eval-as-evidence §1.6 / Governance-doc editing discipline / No shared chat history | 主原则:Type A LLM-first / Type B Orchestration-first / Type C Customer-demo-first;§1.3/§1.4 ownership 边界 | — | `<<PROJECT:>>` 填空 |
| **B** | Doc tier 模型 / prompt-artifact §9 / role registry shape / agent context pack | Milestone framework / four-phase lifecycle / bad-case lifecycle / acceptance-checklist schema | Domain reading lists / domain bad-case shape | — |
| **C** | action-bank 保留窗口 / handoff §0/§1/§2 / archive index pattern | Sprint stanza schema / milestone schema / review findings header | Domain 字段(eval baselines / browser-state) | 各周期实际 ledger |
| **D** | Self-containment invariant / embed-vs-reference 表 / auto-loop-readiness | 各 track prompt skeleton | Domain 嵌入契约 | 实例化 prompt |

### §2.3 Modules(M-X × tier 交叉)

模块 M-Evaluation(light)/ M-Trace(conditional)/ M-Autoloop(conditional)只对应 **某些 track + 某些 stage**;详见 §3 三轨道适用 + §8 模板。模块和 track 不是 1:1。

---

## §3 — 三应用轨道(Δ-14 profile-aware + Δ-15.A2 + Δ-16)

### §3.1 三轨道对照

| 维度 | Type A AI Agent | Type B Agentic Workflow | Type C Demo App |
|---|---|---|---|
| 设计单元 | Skill(phase × resolve-pattern) | SOP step | Off-the-shelf skill(借用社区/团队预制) |
| 控制流 | LLM 自适应、持续推理 | 显式 step / 条件分支 / 验证 gate | LOCAL_ACCEPTANCE_CHECKLIST 兜底 |
| LLM 角色 | 整体控制器 + 内部推理 | 窄任务被 step 调用 | 通常 mock 或最小推理 |
| 主原则(Constitution §1.2)| Rules define boundaries; the model owns semantic understanding | Orchestration owns control flow; the model owns per-step interpretation | Deterministic demo over random; customer demonstrability over completeness |
| Donor 参考 | csagent | hermes(待落地);autoloop 是 dev-time orchestrator,不是 Type B 本体 | fortunes |

### §3.2 Maturity profile(Δ-14 + Δ-15.A4 + Δ-16)

| Stage | Type A | Type B | Type C |
|---|---|---|---|
| **S0 Discovery** | 必需(Δ-15 全套 + Δ-16 7类前置 + industry-synthesis) | 必需(精简集:SOP/tech-constraints/external-APIs/UI) | 必需(轻量:1-page demo brief + off-the-shelf inventory) |
| **S1 First runnable + observability** | 必需 | 必需(SOP test pyramid 替代部分 obs) | 必需(LOCAL_ACCEPTANCE_CHECKLIST) |
| **S1.5 Architecture stress-test** **NEW(Δ-17)** | 必需 5-10d | 必需 3-5d | 可跳过 |
| **S2 Basic eval(Tier-0/1)** | 必需 | 仅当 S2-required event 触发(生产门) | 不需要 |
| **S2.5 Eval validity check** **NEW(Δ-17)** | 必需 3-5d | 触发 S2 后必需 | 不需要 |
| **S3 Eval-driven runtime iter** | 必需 | 仅 S2 触发后 | 不需要 |
| **S3.5 Architecture pivot buffer** **NEW(Δ-17)** | 预算 1-2 次 pivot | 不预算 | 不需要 |
| **S4 Eval framework upgrade** | 必需(periodic fold-back) | 触发后 | 不需要 |
| **S5 Autoloop pre-flight measurement stress-test** **NEW(Δ-17)** | 必需 10d 预算 | 不适用 | 不适用 |
| **S6 Autoloop trustable signal** | 可选 | 不适用 | 不适用 |

**S2-required event**(Δ-14.d):Type B 项目首次发生 (i) 接入终端用户流量;(ii) 承担 SLA / 合规;(iii) 引入 LLM 自主语义决策;(iv) PII / 安全底线进 §1.4 — 任一发生时,Δ-3 决策目录"S2-required event 触发记录"栏锁定,maturity 视角向 Type A 迁移;补 M-Eval + M-Trace 全套。

**S0 prerequisites 列**(Δ-14 修订):Δ-16 7 类前置 × profile 必需集见 §9.10;凡 deferred 必生成 OBS,Type A 必需类目不接受 N/A。

---

## §4 — Domain extension(Δ-7 §L worked-example mention + D2 markdown overlay)

域扩展仅适用于 Type A 内部(workflow / demo 域差异通过 track 切换吸收)。提供 D1(domain manifest YAML)+ D2(domain overlay markdown)组合:
- **D2(主路径)** `A-constitution/AI-agent/domain-overlays/<domain>.md` — 添加 §1.7 forbidden(domain 加项)/ §3.1 layer-set 子集 / §5.1 floors(domain-specific)。AGENTS.md @-include 基线 Layer A + 域 overlay。
- **D1(机器可读补集,Phase 5 延后)** `A-constitution/AI-agent/domain-manifests/<domain>.yaml` — 当 prompt 需要 `{{domain.case_partition}}` 类机器替换时启用。
- **D3(独立 repo)** 仅在 ≥3 domain 同步发布时考虑。

worked example: sales CS reuse 走 D2:复制 `cs.md` 改写为 `sales.md`,机器替换槽位极少,prose 描述为主。

---

## §5 — 5-role 协作 + Δ-9 OBS/autoloop role-split

### §5.1 5-role 注册

| Role | 触发 | 输入 artifact | 输出 artifact | spawned by | reviewed by | 三轨道适用 |
|---|---|---|---|---|---|---|
| **Research Agent**(产品/业务架构师) | Forward-looking question / pattern root-cause | `research-agent.md` + 问题 brief | `docs/research-solutions/*.md` | Human paste | Customer + Tech Lead | A;B 少;C 罕见 |
| **Tech Lead Agent**(原 Deliver,v2 Q3 改名)| 新 milestone 规划 / sub-sprint sequencing / 关闭编排 | role doc + `handoff §0` + research-solution | `sprint_objective.md` / `milestone_objective.md` / `compact/sprint-NNN-dev-prompt.md` / `compact/M<N>-review-prompt.md` | Human paste | Self-review against research scope + Customer | A,B;C 中折回 human |
| **Dev Agent** | Sub-sprint 契约批准 | `compact/sprint-NNN-dev-prompt.md` 自洽 | code diffs + `sprint-NNN-handoff.md` | Human paste / autoloop orchestrator | Code Reviewer + Tech Lead | A,B,C |
| **Code Reviewer Agent** | Sub-sprint close / 触发 §4.3 / milestone close | `compact/M<N>-review-prompt.md` + anti-hardcode kernel | review-findings entry | Human / Tech Lead / autoloop | Human | A(anti-hardcode);B(+workflow-def);C(correctness only) |
| **Acceptance Agent**(NEW 第 5 role)| 预发布 / demo 就绪 | `acceptance-agent.md` + `acceptance-criteria.md` + 风险矩阵 | `LOCAL_ACCEPTANCE_CHECKLIST.md` R-id 证据 | Human / Tech Lead | Human(Customer 之前最后一道) | C 强制;A/B 在发布前采用 |
| **Customer**(人类,on-the-loop **NOT** in-the-loop) | 固定 checkpoint(clarification gate / milestone close / release cut) | Tech Lead 状态报告 + Acceptance 报告 | 决策 / 签字 / 反向问题 | — | — | 全部 |

**Customer on-the-loop 含义**:Customer 不参与每一个 turn / sprint;Customer 只在 (i) Δ-15 brief 签字、(ii) milestone close 验收、(iii) Acceptance 报告决议、(iv) Δ-14 S2-required event 决断 这四类 checkpoint 进入。

### §5.2 工作流 gate(v2 settled)

- **Clarification gate**(S0 期):Δ-15 brief 与 Customer 反复迭代,**未签字态**下游全部阻塞
- **Customer review checkpoint**:每个 milestone close、每个 release cut
- **Multi-layer review chain**:Dev → Code Reviewer → Tech Lead self-review → Acceptance → Customer

### §5.3 Rolling cadence

- **Medium milestones** ~2-4 周(避免大爆炸)
- **Small sub-sprints** ~3-7 天(避免 100-micro-sprint)
- Sprint 关闭即触发 handoff §0 替换、§1 narrative 滚动、§2 archive 入索引

### §5.4 Δ-9 — OBS / autoloop role-split(post-deployment iteration)

**Layer B doc**: `process/post-deployment-iteration.md`(T1,Type A + Type B 适用)

**OBS ≠ R-item**:
- **OBS**(Observation)= 从 case / trace / eval 得到的**行为改进候选**
- **R-item** = runtime / substrate 变更

**两层模型**:
- **L1 Runtime Eligibility Triage**(Tech Lead 拥有)— 若 OBS 依赖未就绪 R-item,先开 R-item;OBS 在 enabler 落地前 not eligible
- **L2 Autoloop Optimization**(Autoloop Driver 拥有)— 一般批量模式,主指标 = 整体 eval + regression profile;OBS-specific metric 仅作 secondary diagnostic

**Role split**(明令禁止 "Tech Lead solves OBS X" framing):
- Tech Lead 拥有 OBS triage / dependency gating / experiment spec / acceptance review
- Autoloop driver 拥有 candidate generation / registry-procedure-prompt 编辑 / batch eval / ranked proposals
- 默认流程:OBS → 一般 outer-loop autoloop 一次 eligible 后

**Anti-pattern**(禁列):
- "Tech Lead solves OBS X" framing — 让 Tech Lead 退化为 operator
- 每个 OBS 一个专属 autoloop — 浪费批量成本
- OBS-specific metric 作为默认主 gate — 触发 gaming

---

## §6 — Bidirectional iteration(donor → aidazi → new project)

### §6.1 单向迁移规则

```
                        ┌───────────────────┐
                        │      aidazi       │
                        │   (templates +    │
                        │   process docs)   │
                        └───────────────────┘
                          ↑                ↓
              (insight feedback        (instantiation +
               docs only)              examples/csagent-reference/
                                       single read-only snapshot)
                          ↑                ↓
                      donor              new project
                      (csagent /         (sales / 物业 / 制造 / ...)
                      hermes /
                      fortunes)
```

- **donor → aidazi**: 仅以 **insight feedback docs**(LessonsLearned-style)流动,donor 自身演化不强制反向写回 aidazi
- **aidazi → donor**: **不存在**。donor 自身保持自治
- **aidazi → new project**: instantiation(@-include + 填空)+ examples/csagent-reference/ 镜像供新项目参照"填空后长什么样"

### §6.2 §L worked-example instance(Δ-7)

`examples/csagent-reference/` 一次性 snapshot,read-only after first instantiation。csagent 后续演化**不**回流到 example。fold-back 方向: 学到新洞见 → templates(live),**不**回流到 example。

显著过期时,开 sub-sprint 整体重建新 snapshot(`examples/csagent-reference-2027-Q1/`),旧目录保留,Δ-4 intermediate 类规则。

两个等价 framing:
- "aidazi 是基于 csagent 抽取的框架" → 读 templates 时引用 examples 看"填空后长什么样"
- "用 aidazi 框架审视 csagent" → 读 examples 检查 csagent 真实做法是否对得上 templates

---

## §7 — Phases(aidazi 自身 bootstrap → 落地 cadence)

| Phase | 范围 | 产物 | 风险 |
|---|---|---|---|
| **P0 aidazi bootstrap** | aidazi standalone repo 初始化;copy framework-template 雏形 + 本文档为 archive | aidazi/AGENTS.md + aidazi/current/(Constitution 3 个轨道 stub)+ aidazi/process/(空 stub) | 零(纯文档 init) |
| **P1 5-role + orchestrator pattern extraction** | 从 csagent docs/teams + autoloop framework/governance 抽取 5-role 定义 → aidazi/B-process/roles/{research,tech-lead,dev,code-reviewer,acceptance}-agent.md | 5 个 role docs + activation prompts | 低(read-only on donors) |
| **P2 M-Evaluation light** | 输出 spec + 4-component contract + 4-tier 金字塔 + adaptor pattern;**no SDK** | aidazi/templates/m-evaluation/{spec.md, contract.yaml, adaptor-pattern.md, tier-pyramid.md} | 低 |
| **P3 M-Trace conditional** | trace contract 抽象(IF generalizable);adaptation + test phase per new project | aidazi/templates/m-trace/{contract.md, adaptation-gate.md} | 中(generalizability 未证) |
| **P4 Type C 折叠轨道** | 抽取 fortunes 模式 → Type C 简化轨道(constitution 极简、acceptance-checklist schema、agent-skill-binding T0 候选) | aidazi/A-constitution/demo/ + aidazi/B-process/four-phase-lifecycle.md | 中(donor 是 live demo) |

---

## §8 — Module templates

### §8.1 M-Evaluation(light)— Δ-15.D + 4-component + 4-tier

**Pyramid**(Δ-11 / Δ-14):
- Tier-0 Safety / PII / 合规底线
- Tier-1 Basic correctness(grounding / tool dispatch / projection)
- Tier-2 Behavioral correctness(UC routing / next action / escalation posture)
- Tier-3 Outcome / contained problem solving

L1/L2/L3 旧三层模型 **deprecated to reference**;Four-Tier 是 v2 confirmed canonical(v2 Q8)。

**4 components**:
- `CaseSpec schema` — 单 case 的输入 / 期望行为 / 范围 / tier 归属
- `Judge contract` — 单 case 的判定逻辑(rubric / 客观判定 / LLM judge)
- `Suite manifest` — case 集合 + tier 比例 + manual review hook
- `Score aggregator` — 跨 case 聚合 + baseline 对比 + regression profile

**Adaptor pattern**:每新项目接入时,提供 adaptor 把项目 runtime trace → CaseSpec compatible 形态;**aidazi 不提供 runtime SDK**。

**Δ-15.D industry-research 必做**(Type A only):
1. Survey 2-3 同领域方案
2. 识别 scope / assumptions / gaps
3. Synthesize own overall plan
4. Specialize for own context(domain knowledge / tools / policy)
5. 产出 `discovery/industry-synthesis-<id>.md`(Δ-12 intermediate artifact;Δ-14 列入 S0 gate)

### §8.2 M-Trace(conditional)— Δ-11 reverse trigger + adaptation gate

Trace contract 抽象**仅在 S1 阶段开始**(observability FIRST);**adaptation+test phase per new project** — 框架不强制特定 trace schema,但提供 portable shape:
- `turn_id` / `session_id` / `phase_id` / `tool_call_seq` 必填
- `projection_payload`(送入 LLM 的上下文,redact 后)推荐
- `tool_call_payload` / `tool_response_payload` 推荐
- `llm_response_raw` 推荐(eval 与诊断同时需要)

**Reverse trigger**(must add observability when ...):session 无法 replay / bad-case 无法 root-cause / projection 漂移与代码不一致。Δ-11 反向触发表完整版在 §9.6。

### §8.3 M-Autoloop(conditional, T1)— Δ-9 OBS triage + autoloop optimization

仅 Type A;Type B 不适用;Type C 不适用。

**条件适用**:
- S5 entry condition: eval 框架经 S2/S2.5 验证可信、Δ-9 anti-gaming forbidden list 已落地
- 主指标 = 整体 eval + regression profile(**不**是 OBS-specific metric)
- 默认运作:OBS → 一般 outer-loop autoloop;每个 OBS 专属 autoloop 是 anti-pattern

**Δ-9 forbidden list**(必须写入 autoloop driver role doc):
- "Tech Lead solves OBS X" framing
- 每 OBS 一专属 autoloop
- OBS-specific metric 作主 gate

---

## §9 — Layer B process docs(全部 Δ Layer-B 添加项)

### §9.1 Δ-2 — `process/domain-discovery-process.md`(T0)

P0 加载;Research Agent 主导执行;Customer 提供答案。

**三维度问题集**:
- **D1 业务调研**: agent 前业务怎么运转 / human owner 期望 / agent vs human-only vs human-on-loop 切分 / 业务方对"成功"定义
- **D2 用户问题分类**: 真实样本聚类 / 频次 / 长尾 / intent-switch + 复合 intent 占比
- **D3 边界 / 集成 / 业务指标**: 既有系统 / 硬边界(合规/PII/安全)/ 业务侧 metric / agent 贡献的可分离信号

**输出物**(Δ-4 intermediate 类,绑定 P0):
- `discovery/business-map.md`
- `discovery/user-problem-taxonomy.md`
- `discovery/boundary-and-metrics.md`

**下游连接**:D2 → §10 Type A runtime skeleton intent 集合;D3 → Δ-3 decision catalog tools / policy / eval 决策;D1 → Customer barrier-break event 列表。

### §9.2 Δ-3 — `process/tech-architecture-decision-catalog.md`(T0)

Research + Tech Lead 联合产出;紧跟 Δ-2 之后。

**8 项决策**:

| # | 决策项 | 选项集 | 推迟许可 |
|---|---|---|---|
| 1 | **应用类型**(轨道选择) | Type A / B / C | 不允许(必 P0 决);**绑定 S2-required event 触发记录槽位**(Δ-14 修订) |
| 2 | 抽象层次 | single-agent / multi-agent / no-agent | 不允许 |
| 3 | 上下文投影模型 | per-turn 全量 / 增量 / projection-by-skill | 允许 P1 |
| 4 | 状态管理 | stateless / session / cross-session / 持久 ledger | 允许 P1 |
| 5 | 记忆 | 无 / 短期 / 长期 / RAG-as-memory | 允许 P1 |
| 6 | 工具定义 | enum / yaml schema / dynamic registry | 允许 P1 |
| 7 | Policy / gadgets | prompt-level / runtime-gate / 混合 | 允许 P1 |
| 8 | 评估 | yes / no / spec-only(M-Eval-light)/ 全量 | **必 P0**(Type A 必 yes;Type B 看 S2-required event;Type C 必 no) |

**核心原则**:决策**目录**是 T0;**决策结果**是 T2/T3。框架不替项目选,框架只确保项目知道自己选过。

### §9.3 Δ-4 — Doc lifecycle classification(live vs intermediate)

加到 `doc_governance.md` 的强制规则:每个新 doc front-matter 必填 `doc_category: live` 或 `intermediate`。

| 维度 | `live` | `intermediate` |
|---|---|---|
| `last_reviewed` | 必填,有 cadence | 不要求,创建即冻 |
| `source_of_truth` | code path / 另一份 live doc | 创建时的 sprint context |
| 修改许可 | 周期性 fold-back 允许 | 仅事实性 typo |
| 命名 | 不带 sprint ID | **必须**带 source sprint ID |
| 例子 | `iteration_governance.md` / `doc_governance.md` | `compact/sprint-NNN-dev-prompt.md` / `docs/sprints/*` / discovery 输出物 |

**根因表述**:用户被烧过的具体路径是"生成的设计 doc → 喂给 coding agent → 生成 code → doc 不再被更新 → 半年后所有人按过期 doc 推理"。根因不是没 fold-back,根因是没区分 intermediate 与 live。

### §9.4 Δ-5 — Context-passing efficiency(Constitution refine)

Constitution 新增条款:

> Context-passing 必须同时满足 **sufficient**(下游不需要回溯上游会话)**AND efficient**(不浪费 token / 不强制下游加载无关 context)。任何 prompt artifact 的发布者(Tech Lead / Dev / Customer)必须为该 artifact 声明显式 token budget。

**操作化** front-matter:

```yaml
context_budget:
  target_tokens: 8000
  load_list: [<必须加载清单>]
  do_not_load: [<显式排除清单>]
self_contained: true
```

### §9.5 Δ-10 — `process/doc-responsibility-matrix.md`(T0)

**问题**: AGENTS.md / CLAUDE.md / iteration_governance / action_bank / handoff / doc_governance 互相重叠;全加载导致 context bloat;csagent 44.8KB→20.4KB Layer-A 拆分是教训代价。

**8 字段 schema**(7 字段 + Δ-12 新增 artifact_type):
- `owner`(单一负责 role)
- `scope_in`(本 doc 承担的内容范畴)
- `scope_out`(显式不在本 doc 的内容)
- `load_discipline`(always-load / on-demand / by-role)
- `overlap_policy`(同主题在 ≥2 doc 时谁是 canonical)
- `size_target`(KB)
- `split_trigger`(超过 size_target 后的拆分判据)
- `artifact_type: live_ledger | intermediate | append_only_archive | reference_contract` **(Δ-12 新增)**

**规则**:
1. 写新 doc → 必填 matrix 入口;无入口不得 merge
2. 超 size_target → split-trigger 审查自动触发
3. 同主题双 doc → 必须 mark `defer_to` 一份为 canonical
4. load_discipline 是**契约**不是描述

`artifact_type` 枚举权威表是 Δ-12 taxonomy(§9.7);`split_trigger` 对 `live_ledger` 必填具体阈值,对 `append_only_archive` 填 `n/a — append only`。

### §9.6 Δ-11 — `process/capability-staging-roadmap.md`(T0)— **REVISED per Δ-17**

**v3.2 完整 stage 序列**(S1.5 / S2.5 / S5 为 Δ-17 新增,S3.5 为 Δ-17 新增 architecture pivot buffer):

| Stage | 简称 | 关键产物 | Type A | Type B | Type C |
|---|---|---|---|---|---|
| **S0** | Domain understanding | Δ-2 discovery + Δ-3 decision catalog + Δ-15 brief + Δ-16 prereqs | 必需 | 必需 | 必需(轻量) |
| **S1** | First runnable + observability | First runtime + observability/trace FIRST;manual cases;NO eval framework;NO autoloop | 必需 | 必需 | 必需 |
| **S1.5** **NEW** | Architecture stress-test 5-10d | Manual cases 10-15 / trace coverage 检查 / 架构再评估;若 pivot 在 deck → 现在 pivot | 必需 | 必需 3-5d | 可跳 |
| **S2** | Basic eval(Tier-0/1) | Manual CaseSpec 手工;case→score→review chain;证明尺子准 | 必需 | S2-required event 触发后 | 不需要 |
| **S2.5** **NEW** | Eval validity check 3-5d | "Intentional break → eval must catch" ≥3 examples;manual×eval 一致率 >90% | 必需 | S2 触发后 | 不需要 |
| **S3** | Eval-driven runtime iter | OBS-driven iteration(Δ-9);Tier-2/3 扩展 | 必需 | S2 触发后 | 不需要 |
| **S3.5** **NEW** | Architecture pivot buffer | 1-2 次 pivot 预算;不视为 failure | 必需 | 视情况 | 不需要 |
| **S4** | Eval framework upgrade | 周期 fold-back;eval 自身随系统能力升级 | 必需 | 触发后 | 不需要 |
| **S5** **NEW** | Autoloop pre-flight measurement stress-test 10d | 首批 autoloop overnight 视作 eval framework stress test;预期 5-10d 修测量框架(NOT runtime) | 必需 | 不适用 | 不适用 |
| **S6** | Autoloop trustable signal | Autoloop 候选可被 manual 复核通过 | 可选 | 不适用 | 不适用 |

**反向触发表**(must add eval / must add autoloop / must demote eval / must pause autoloop)— 详 Δ-11 文件;Δ-13 软化了原 "F 架构锁" → "stage-stable heuristic":

> F 阶段稳定(stage-stable):启发式提示(非门控): 近 5-10 commit 中 runtime 路径占比 ≤ ~20% 且 semantic 路径占比 ≥ ~60%,持续 ≥ 3 个 sub-sprint;由 Tech Lead+human 主观判定,可作为升档 S3 的一项支持证据。**不是**自动门控,**不是**全局锁。

**Anti-patterns**(Δ-11 显式标注):
- S2 启用自动 case generation 放大坏 case 设计
- S1/S2 开 autoloop 因 eval 不可信无法分辨好坏变更
- 不区分 R-item vs OBS(Δ-9)强迫 autoloop 做不可能事
- 把 S5 首夜 discard 视为 runtime 问题(Δ-17 P3)

**动态过程免责**(Δ-13.c 写入 Δ-11):

> 架构相对稳定是 per-stage 属性,不是永久状态。新增主功能 / 引入新主路径 / 跨越生产部署边界 → 预期暂时回到 S1/S2 重走 observability + eval。这是**设计期望**而非倒退。

### §9.7 Δ-12 — `process/artifact-taxonomy.md`(T0)

**11 artifact 总表**:

| artifact | 触发 | 生产者 | 消费者 | lifecycle | 留存 |
|---|---|---|---|---|---|
| `action_bank.md`(open) | dev/Tech-Lead 发现 R-item / OBS | dev / Tech Lead | Tech Lead(规划) / dev(领取) | live ledger | 仅 open 项;关闭即外迁 |
| `action_bank_archive.md` | open 项关闭 | Tech Lead(关闭时) | human(审计) / Tech Lead(查重) | append-only | 永久 §A/§B/§C 分节 |
| `proposals/*.md` | 研究 / Tech Lead 前瞻设计 | research / Tech Lead | Tech Lead(在 sprint 引) / human | intermediate(待裁决) | `status: proposal/partial/deferred/superseded` 不删 |
| `diagnostics/*.md` / `failure-briefs/` | 审计 / bad-case 根因 / trace 投影 | dev / research | Tech Lead(转 R-item) / human | intermediate | 转化后留存 |
| `sprint_objective.md` | 本 sub-sprint 契约 | Tech Lead | dev(执行) / reviewer(对账) | live(当前 sub-sprint) | 关闭后归档 `docs/sprints/` |
| `milestone_objective.md` | 当前 milestone 北极星 | Tech Lead | Tech Lead(规划) / human | live(当前 milestone) | 关闭后归档 `docs/milestones/` |
| `handoff.md §0` cold-start | 每个 sub-sprint/milestone 关闭 | Tech Lead | 所有 agent 冷启动 | live(永远当前) | 整段替换 |
| `handoff.md §1` narrative | 当前 milestone + 上一关闭 | Tech Lead | 需上下文叙事的 agent | live(retention window) | 保留窗口 = 当前 + 上一关闭 |
| `handoff.md §2` archive index | milestone 关闭 | Tech Lead | human / 任何回溯 | append-only index | 永久 |
| `codex-findings.md` | reviewer 出具裁决 | Code Reviewer | Tech Lead(收口) / human | intermediate | 收口后归档 |
| `research-solutions/*.md` | research 完成调查 | research | Tech Lead(转 sprint) | intermediate(待消费) | 消费后归档 |

**每 role 必读 artifact 清单**:

| role | 必读 | 按需 | **禁读** |
|---|---|---|---|
| dev | `sprint_objective` / `handoff §0` / `action_bank`(领取范围) | `diagnostics`(R-item 来源)/ `proposals`(sprint 引) | `codex-findings`(关闭前不看)/ `milestone_objective` |
| Tech Lead | `sprint_objective` / `milestone_objective` / `action_bank` / `handoff §0+§1` / `codex-findings`(收口时) | `proposals`(选材)/ `diagnostics`(转 R-item)/ `research-solutions` | `action_bank_archive`(仅审计) |
| Code Reviewer | `sprint_objective` / 本次 PR 相关 `diagnostics`(若 sprint 引) | `handoff §0`(冷启动) | `action_bank` / `milestone_objective` / `research-solutions` |
| research | `proposals` 相邻 / `diagnostics/failure-briefs`(若相关) | `action_bank`(看 OBS 已在动) | `sprint_objective` / `codex-findings` |
| Acceptance | `acceptance-criteria` / 本 release 范围 `diagnostics` / 上一 acceptance-checklist | `handoff §0` / `milestone_objective` | `action_bank`(运行期不看) |

**action_bank open/archive 拆分规则**:
- **size 触发**: > 800 行强制扫荡
- **count 触发**: 累计 close ≥ 10 条未迁移强制
- **cadence 触发**: 每 milestone 关闭必扫
- 关闭即迁移;原 anchor 留 1 行 stub `#R-XX → archive §A.YYYY-MM`
- 提交信息: `action_bank archive sweep — N items moved (size=X→Y lines)`
- 同步检查反向引用并修补(避免 2026-06-01 漂移)

**Human cold-start cheatsheet**(1 页):

| 想看 / 决定 | 去看 | 何时 |
|---|---|---|
| 现在 agent 在干啥 | `sprint_objective.md` | 任何时候 |
| 这个 milestone 想达到啥 | `milestone_objective.md` | milestone 启动 / 收口 |
| 上次会话留了什么状态 | `handoff.md §0` 表 | 每次回到项目 |
| 最近一个 milestone 叙事 | `handoff.md §1` | 想理解最近背景 |
| 历史 milestone 怎么找 | `handoff.md §2` archive index | 回溯老 milestone |
| 现在 backlog | `action_bank.md` | 决定下一 sub-sprint |
| 历史上干过啥 / 为啥 | `action_bank_archive.md` | 审计 / 查重 / 追溯 |
| 前瞻设计 | `proposals/` | 规划下一 milestone |
| 审计 / 根因 | `diagnostics/` / `failure-briefs/` | 出 bad-case 时 |
| Codex 裁决 | `codex-findings.md` | sprint/milestone 收口 |
| Research 方案 | `research-solutions/` | Tech Lead 选材 |

### §9.8 Δ-13 — Architecture-stable softened(stage-stable heuristic)

**重命名**: "架构锁" → "**架构相对稳定 / 阶段稳定**"(stage-stable / locally stable)— 仅 per-stage 属性,不主张全局或长期。

**操作性启发式**(非门控):见 §9.6 F 行。

**框架不提供脚本**:`git log -n 10 --stat -- <runtime-paths>` 一类 grep/git 例子作为方法论附录;判断权归 Tech Lead + human。

### §9.9 Δ-15 — `process/agent-design-elicitation.md`(T0;heuristic Q&A 非 checklist)

**Part A — 6 mandatory questions**(Δ-15.A1: 需 human-signoff,front-matter 增 `human_signoff` 字段):
1. **Domain** 行业 / sub-area / 范围 — human only
2. **Goal** 1 句可量化成功 — human only
3. **Problems** 有界清单(非模糊集) — human only
4. **Method** intent-classification + multi-phase pipeline?OR workflow?OR 单 LLM 调用? — 框架引导 + human 选
5. **Knowledge** 领域知识 inventory + 来源 + freshness 策略 — human(domain)+ 框架(schema)
6. **Boundary** agent-loop 拥有 vs 外部 harness 保证(Constitution §1.3/§1.4) — 框架 Q&A + human 选

**Δ-15.A1 human-signoff 规则**:
- 未签字 brief 下游不得消费(Δ-3 / Δ-11 / sprint_objective 引用阻塞)
- 已签字 brief 进入 Δ-12 intermediate 类,进 §0 cold-start 指针表
- **重签触发**: 六必答任一实质变更 / Part D 综合稿被替换
- Part B 单纯增删工具/技能条目**不**触发重签(增量,non-breaking)

**Part B — 4 inventories(profile-aware,Q3 + Δ-15)**:
- **Type A**: Knowledge / Tools / **Skills** / Policy
- **Type B**: Knowledge / Tools / **SOPs**(替代 Skills)/ Policy
- **Type C**: Knowledge / Tools / **Off-the-shelf Skills**(借用)/ Policy(可极简)

**Part C — Tool vs Skill decision tree**(**仅 Type A**):
- 原子能力 + agent 全控 → tool
- 子任务有 mandatory tool sequence + adaptive logic → skill
- 跨多 flow 重复模式 → 包成 skill
- >15-20 skills → 检查分解(csagent 6 skills = phase × resolve-pattern granularity,VERIFIED)
- **Type B**: Part C 替换为 "SOP step 划分指引"(何时一动作独立成 step:有独立 verification gate / 失败回退路径 / 业务可观测)
- **Type C**: 简化(see §13.1 PB5)— 只问"有没有现成的;有就用,没有拼 tool"

**Part D — 0→1 industry research methodology**(Δ-15.A2 profile-aware):

| Profile | Part D 行业调研 | 替代物 | 输出 |
|---|---|---|---|
| A · AI Agent | **必做**(MUST) | 无 | `discovery/industry-synthesis-<id>.md`(2-3 家方案对比 → 综合 → 本场景特化) |
| B · Agentic Workflow | 不要求 | SOP / 流程设计调研(严格可选) | 若做 `discovery/sop-survey-<id>.md`;不做则 brief 显式 "SOP survey: skipped, rationale: <…>" |
| C · Demo App | 不要求 | 现成技能清单(off-the-shelf inventory) | `discovery/offshelf-skill-inventory-<id>.md`(可极简,bulleted) |

**Δ-15.A4 PB2 隐式答**: Part D Type A 是 S0→S1 硬 gate(与 brief 人签字并列);Type B 否;Type C 否(包含在 1-page demo brief 内即可)。

### §9.10 Δ-16 — `process/agent-creation-prerequisites.md`(Layer B, T0)

**doc tier**: durable-connective;**review_cadence**: 每 5 个 agent 创建实例后回看。

**Why prerequisites**: Δ-15 elicitation 的有效性依赖**事实输入已经在场**。若 BRD/PRD/技术栈/知识语料/话术/外部 API/UI 在 elicitation 启动时不存在,六必答只是"拍脑门胡搞"。用户 CS Agent 1.0 经验为锚:这些不是 agent 设计的产物,而是 agent 设计**所消费的原料**。

**7 类前置物**(domain-agnostic):

| # | 类别 | 范围 | 提供方 | 就绪判据 |
|---|---|---|---|---|
| 1 | **BRD** | 业务问题 / 目标用户 / 商业边界 | 业务方 / PM | 含"必须有"清单,业务方签字 |
| 2 | **PRD** | 产品形态 / 用户旅程 / KPI | PM | 含 KPI 定义,PM 签字 |
| 3 | **技术约束** | 基础栈 / 平台限制 / infra / 合规 | 架构 / SRE | 硬 vs 软约束分列,硬约束有引用源 |
| 4 | **知识语料** | FAQ / 领域知识 / 政策手册 / 历史会话 | 业务 + 内容运营 | 可被检索路径(grep/vector/SQL)消费;有 schema |
| 5 | **固定话术** | 模板 / canned reply / 法务定稿 | 法务 + 业务 | 每条有触发条件 / 用途标注 |
| 6 | **外部系统清单** | API / MCP server / DB / 第三方 | 架构 + owner | 含 endpoint / auth / SLA / rate-limit;**对接联系人**已知 |
| 7 | **UI 定义** | 界面 / 输入方式 / 渲染约束 / 多端 | 设计 + 前端 | 至少有线框图;消息形态(纯文本/富文本/卡片)已定 |

**Profile-aware 必需集**(与 Δ-14 交叉):

| Profile | 必需 | 可选 | 替代 |
|---|---|---|---|
| A | 1,2,3,4,5,6,7(全部) | — | UI 多端可分阶段;次端 deferred 允许 |
| B | 3 + 6 + 7(若面向人) + **SOP 定义**(替代 1+2) | 4,5 | BRD/PRD 由 SOP 流程图吸收;FAQ/话术大多数 workflow 不需要 |
| C | **1-page demo brief**(替代 1+2)+ **off-the-shelf skill inventory 指针**(替代 4+5) | 3,6,7 | 技术约束可极简;外部系统通常 mock |

**Gate 逻辑**:
- **READY**: 文档存在 + 满足判据;路径登记入 brief `prerequisites:` front-matter
- **DEFERRED**: 不存在 / 不满足,但允许暂缓;填 rationale + 预期补齐时间;**自动生成 OBS-id**(Δ-9),标签 `prereq-deferred`;触发 brief 实质变更则触发 Δ-15 重签
- **NOT_APPLICABLE**: 仅 Type B/C 可选类目可用;Type A 必需类目不接受 N/A

Brief front-matter:

```yaml
prerequisites:
  brd: { status: ready, path: "<...>", verified_on: <YYYY-MM-DD> }
  prd: { status: deferred, rationale: "<...>", obs_id: OBS-<n> }
  ...
```

**Anti-pattern**:
- 前置缺失硬跑 elicitation → Part A 空中楼阁,反复重签,Δ-3 决策被推翻
- "前置就绪"误归为 Tech Lead 工作 — Tech Lead 只**核对**,不**生产**;生产方在 (b) 列已列明
- deferred 兜底全部缺失 — 必须显式 OBS;Type A 1/2/3/6 任一 deferred 应触发"是否还应启动此 agent"反问

### §9.11 Δ-17 — `process/common-detours-and-warnings-typeA.md`(T0;Type A only)— **FULL DRAFT**

#### (a) Mission disclaimer + scope

**定位**: "踩过坑的过来人在旁边提醒"。Δ-17 不是 detour-skipper。

**认知不到位的弯路必须自己走**: framework 不承诺"跳过所有弯路"。每一类弯路的第一次走过都是认知升级的必经过程,因为弯路本身教你识别下一次同类弯路的预警信号。框架的价值是 **(1) 给弯路命名;(2) 给你定位**(你现在在哪个 P 里)**;(3) 给你退出方向**(不是回头路,而是更近的出口)**。下一个 agent 的创造者带着 Δ-17 第二次走的时候,识别 P1 的窗口期会从 4 周缩到 1 周**。

**范围**: 仅 Type A AI Agent。Δ-17-B(Type B detours)/ Δ-17-C(Type C detours)为独立 parallel docs,空启动,待 hermes / fortunes 各自首例 lifecycle 完成后填充。

#### (b) csagent 54-day timeline 抽取的 4 类结构性弯路

##### P1 — Spec-first / Data-late 鬼影评测期

| 维度 | 内容 |
|---|---|
| 症状预警(可观察) | spec 完整(UC / FAQ / tool spec / scripts ready 4/22);真实 entity data 远晚落地(5/20,4 周 gap);eval framework 在 gap 期搭建产生**不可信信号** |
| 实际代价(csagent) | ~2 周 eval-driven iteration 跑在错误 baseline 上;Sprint 1-16 部分失效 |
| 触发避免方式 | Δ-16 prereq #4(知识语料)gate 判据包含"真实数据在 repo,不只是 spec";**必须 READY** 才进 S2 |
| 在弯路里时怎么退出 | 暂停 eval-driven iteration;补全 data load;re-baseline;前 1-2 周 iteration 视作 forensic only |
| 对应新增 stage | 触发 Δ-16 与 Δ-11 的 S2 进入判据 |

可观察 grep 测试:KB JSON / mock business exports 不在 repo;eval 信号与 manual review 出现持续 divergence。

##### P2 — Eval-before-architecture-stable 双修期

| 维度 | 内容 |
|---|---|
| 症状预警 | eval v1(4/23-5/03)搭在 Agent 1.0 monolithic prompt 架构上;5/17 架构 pivot 到 Skill Registry;eval framework 5/21-5/25 (M3-Eval / M4 / M5) 再升级;L3 judge 哲学从"path checking" → "outcome-oriented" 重写 |
| 实际代价(csagent) | eval framework 搭了两次;~5d re-architect |
| 触发避免方式 | **新增 S1.5 "架构压测期" 5-10d**(manual review + observability/trace coverage 检查 + 架构再评估);在搭 eval framework 之前;若 pivot 需要 → 现在 pivot |
| 在弯路里时怎么退出 | 即使 S2 中途,architecture pivot 在 flight 中 → demote eval 回 S1.5 |
| 对应新增 stage | **S1.5** |

可观察 grep 测试:5/05 单日 19 commits(Sprint 2-6 rolling);mid-milestone pivot 提议在 backlog;broad runtime restructure 提议。

##### P3 — Autoloop 暴露测量 bug 误判为 runtime bug

| 维度 | 内容 |
|---|---|
| 症状预警 | 5/31 首个 overnight autoloop 40+ 轮全部 tier 0 discard;首次解读"runtime 有 bug";实际 6/01-6/05 trace-dive 揭示 eval framework bugs(simulator role-inversion / vacuous-pass / stall-not-gated) |
| 实际代价(csagent) | ~5d 误把 failure 归因 runtime;M-Auto-4 暂停 |
| 触发避免方式 | **新增 S2.5 "评测有效性验证期" 3-5d**("intentional break → eval must catch" 验证 ≥3 examples 进 S3);**新增 S5 10-day buffer** 把 autoloop 作 eval-stress-test(planned 不是 crisis) |
| 在弯路里时怎么退出 | 暂停 autoloop;trace-dive 手工;隔离 eval bugs vs runtime bugs |
| 对应新增 stage | **S2.5 + S5** |

可观察 grep 测试:autoloop discard rate >80% 在 tier 0 首批;manual eyeball of "discarded" candidates 与 eval verdict 持续不一致。

##### P4 — Mid-milestone 架构 pivot 实质是 S1 收敛过早信号

| 维度 | 内容 |
|---|---|
| 症状预警 | 5/17 M2 mid-flight pivot 从 "Skill foundation" 到 "Skill Registry abstraction";pivot 本身正确(问题被识别) |
| 实际代价(csagent) | M1 Sprint 1-16 部分被 M2 refactor 吸收/废弃;心理成本 |
| 触发避免方式 | **新增 S3.5 "架构 pivot buffer"** — 早期 Type A 预算 1-2 次 pivot;不 frame 为 failure |
| 在弯路里时怎么退出 | 在 sub-sprint 边界宣告 pivot(不在 sprint 中段);作为 Δ-3 decision revision 浮出 |
| 对应新增 stage | **S3.5** |

可观察 grep 测试:milestone 进行 1-2 sprint 后强烈感觉"we need a different abstraction"。

#### (c) Actual vs Recommended timeline 对照

| Stage(recommended) | csagent actual | csagent 跳过 / 折叠 |
|---|---|---|
| S0 design | ①② | ✓ same |
| S1 first runnable | ③ | ✓ same |
| **S1.5 arch stress-test** | **SKIPPED** → ④ direct | P2 根因 |
| S2 eval basic(Tier-0/1 only) | ④ eval v1 全 L1/L2/L3 一次性 | L3 哲学锁太早 → P2 |
| **S2.5 eval validity check** | **SKIPPED** | P3 根因 |
| S3 eval-driven runtime iter | ⑤ Sprint 1-35 / 5/04-5/18 | data 5/20 落地 → P1 |
| **S3.5 arch pivot buffer** | M2 pivot 5/17 unplanned | P4 |
| S4 eval framework upgrade | ⑥ M3-M5 5/21-5/25 | done but framed as crisis vs normal event |
| **S5 autoloop pre-flight measurement stress-test** | **SKIPPED** → ⑦ autoloop | P3 |
| S6 autoloop trustable signal | M-Auto-5 close 6/05 | 10d unplanned actually spent fixing eval |

#### (d) 3 个新增中间 stage 完整规格

**S1.5 架构压测期(5-10d)**:
- Entry condition: S1 first runnable demo 能 end-to-end 完成 ≥5 manual case scenarios
- Activity: manual case 10-15 scenarios + observability/trace coverage check + 架构再评估
- Exit gate: 无架构 pivot 提议 pending;trace coverage ≥80% per turn
- 此 gate 阻断的 anti-pattern: 在 S1.5 之前搭 eval framework(P2)

**S2.5 评测有效性验证期(3-5d)**:
- Entry condition: Tier-0 + Tier-1 eval 能 end-to-end 跑在 ≥10 CaseSpecs 上
- Activity: "intentional break → eval must catch" 验证 ≥3 distinct break types(semantic break / tool-call break / projection break);manual review × eval verdict cross-check on 10+ cases
- Exit gate: ≥3 intentional breaks 被捕获;manual×eval 一致率 >90%
- 此 gate 阻断的 anti-pattern: 在 S2.5 之前开 autoloop(P3)

**S5 Autoloop 前置: 测量 stress-test(10d 预算)**:
- Entry condition: S4 eval framework upgrade 完成;data 完整;Δ-9 anti-gaming forbidden list 已落地
- Activity: autoloop 首夜 **被视作 eval-framework stress test**;预期 5-10d 修测量框架(NOT runtime);planned for it
- Exit gate: 第 2 个连续 overnight autoloop run 产生 ≥1 candidate 同时通过 autoloop 与 manual review
- 此 gate 阻断的 anti-pattern: 把首夜 discard 视作 runtime issue(P3)

#### (e) Pattern 通用表格(P1-P4 每条已在 §9.11(b) 渲染为表格)

每 P 都包含: 症状预警(可观察) / 实际代价(csagent) / 触发避免方式 / 在弯路里时怎么退出 / 对应新增阶段。

#### (f) Cognitive-detour disclaimer(明确写入)

> 本框架无法替你跳过弯路 — 每一类弯路的第一次走过都是认知升级的必经过程,因为弯路本身教你识别下一次同类弯路的预警信号。框架的价值不是 detour-skipper,而是 **(1) 给弯路命名**;**(2) 给你定位**(你现在在哪个 P 里);**(3) 给你退出方向**(不是回头路,而是更近的出口)。下一个 agent 的创造者带着 Δ-17 第二次走的时候,识别 P1 的窗口期会从 4 周缩到 1 周。

#### (g) §L Worked Example cross-reference

csagent 54-day timeline 是 Δ-17 的 **the** worked example。完整 date-stamped 阶段 ①-⑦ + commit counts + activity-day counts 进入 `examples/csagent-reference/timeline-54-day.md`(从 §L 引用,**不**内嵌于 Δ-17)。

#### (h) Open questions for first-trial

- S1.5 / S2.5 / S5 预算天数为估计值;首例 Type A 用 Δ-17 时应微调
- P5-Pn(更多 pattern)将随更多 Type A agent 被构建涌现;Δ-17 是 append-extensible
- Δ-17-B / Δ-17-C placeholders 空启动;待 hermes / fortunes 各自首例 lifecycle 完成后填充

### §9.12 Δ-17-B / Δ-17-C placeholders

#### Δ-17-B — `process/common-detours-and-warnings-typeB.md`(T0;Type B only)

**Status**: EMPTY placeholder。Populate when first hermes-like Type B project completes lifecycle. 当前已知占位条目:SOP 设计粒度过细 / step verification gate 缺失 / cross-step 状态污染 — 但尚无 worked example。

#### Δ-17-C — `process/common-detours-and-warnings-typeC.md`(T0;Type C only)

**Status**: EMPTY placeholder。Populate when first fortunes-like Type C project completes lifecycle。当前已知占位条目:off-the-shelf skill 选型失误 / mock 不一致 / demo cut 前合规漏审 — 但尚无 worked example。

---

## §10 — Type A runtime architecture skeleton(Δ-6;PORTABLE-SKELETON)

新增 Type A 推荐运行架构骨架。v2 §J/§K 给了 M-Eval / M-Trace 但未给 "agent 内部 turn loop 长什么样"。

```
                          ┌─────────────────────────────┐
incoming user turn ──────▶│  intent classification gate │  ← 单一入口
                          └──────────────┬──────────────┘
                                         │
                  ┌──────────────────────┼──────────────────────┐
                  │                      │                      │
              intent_X               intent_Y               intent_Z
                  │                      │                      │
                  ▼                      ▼                      ▼
        ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
        │ phase pipeline X │   │ phase pipeline Y │   │ phase pipeline Z │
        └─────────┬────────┘   └─────────┬────────┘   └─────────┬────────┘
                  │                      │                      │
                  └──────────────────────┼──────────────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │ intent-switch hook  │  ← 任意 turn 可触发
                              └─────────────────────┘  ← 可切回(carry-over state)
```

**每 phase 内部契约**(T1):

```yaml
phase:
  name: <T2-domain-specific>      # 比如 propose / triage / resolve / confirm
  inputs:
    - projected_context           # 来自 Δ-3 decision #3
    - state_handle                # 来自 Δ-3 decision #4
  steps:
    - model_interaction           # LLM 调用 + tool-calls
    - tool_execution              # capability-gated(Δ-3 decision #6)
  exit_condition:                 # 条件驱动,LLM 半决策
    - to_next_phase_if: <cond>
    - to_intent_switch_if: <cond>
    - to_escalate_if: <cond>
```

**T1 vs T2 vs T3 边界**:
- **T1 portable**: intent gate / multi-phase pipeline / per-phase = model+tool+conditional-progression / intent-switch with carry-over
- **T2 domain-specific**: phase 的具体名字与个数(csagent: propose→triage→resolve→confirm→escalate→close,六阶;别 domain 可三阶)
- **T3 project-specific**: phase 内部的 tool 集合、policy 表达式、grounding rules

csagent 的具体 phase 名字进 §L worked example,不进框架骨架。

---

## §11 — Pitfalls(v1 §G + Δ-9 + Δ-11 + Δ-17 cognitive-detour cross-ref)

- **削足适履(over-generalize CS into Layer 0)** — Trip-wire: 任何 `<<PROJECT:>>` slot 例子 CS-only 且其他 track 不会自然填。Mitigation: body-leak greps per track。
- **Over-engineering(framework too heavy for demo)** — Trip-wire: demo 项目实例化 Layer A >15 KB 或 Layer B mandatory load >10 KB。Mitigation: Type C 显式 opt-out。
- **Lock-in(hard to fold back insights)** — Trip-wire: fold-back proposal 坐 >2 milestone closes。Mitigation: milestone-close 加 framework-fold-back-review 步。
- **Implicit domain coupling** — Trip-wire: Layer A/B doc 引 domain-specific 概念无 slot 或标记。Mitigation: 每个 framework PR 跑 body-leak grep;reviewer 强制。
- **Skill sprawl** — Trip-wire: 一个 role doc 列 >5 mandatory skills。Mitigation: per-role allowed skills list + T0/T1/T2 tagging。
- **Per-track 漂移** — Trip-wire: 同概念在 ≥2 track 措辞实质不同。Mitigation: T0 chunks 在 `T0-shared/` 通过 @-include 复用;override 是另一文件不是 edit。
- **Premature instantiation** — Trip-wire: track 模板在被项目用过之前已完写。Mitigation: extract patterns FROM working projects (csagent→AI-agent track; autoloop→workflow; fortunes→demo) rather than design top-down。

**Δ-9 forbidden(post-deployment)**:
- "Tech Lead solves OBS X" framing(turns deliver into operator)
- 每 OBS 一专属 autoloop(浪费批量成本)
- OBS-specific metric 作主 gate(触发 gaming)

**Δ-11 anti-patterns**:
- S2 启用自动 case generation 放大坏 case 设计
- S1/S2 开 autoloop(eval 不可信无法分辨好坏)
- 不分 R-item vs OBS

**Δ-17 cognitive-detour disclaimer**(cross-ref §9.11(f)): 框架不承诺跳过弯路;价值是命名+定位+退出方向。

---

## §12 — §L Worked Example Instance(Δ-7 + Δ-17(g))

**目录约定**:

```
aidazi/
├── current/                          # 框架文档(live)
├── process/                          # Layer B 流程文档(live)
├── templates/                        # 各 Module 的填空模板
└── examples/
    └── csagent-reference/            # §L 落地
        ├── README.md                 # "这是 csagent 的填空快照"
        ├── snapshot_date: 2026-06-06
        ├── source_commit: <hash>
        ├── doc_category: intermediate
        ├── discovery/                # Δ-2 三维度的 csagent 答案
        ├── decisions/                # Δ-3 8 项决策的 csagent 选择
        ├── runtime-skeleton/         # Δ-6 骨架的 csagent 填法
        │   └── phases/{propose,triage,resolve,confirm,escalate,close}.md
        ├── m-eval/                   # M-Evaluation 模板填空
        ├── m-trace/                  # M-Trace 模板填空
        └── timeline-54-day.md        # **NEW from Δ-17 §9.11(g)**
                                      #   ① S0 design 4/15-4/22
                                      #   ② Δ-15 brief 4/19-4/22
                                      #   ③ S1 first runnable 4/22-5/02
                                      #   ④ S2 eval v1(full 三层) 4/23-5/03
                                      #   ⑤ S3 eval-driven iter 5/04-5/18(含 5/17 M2 pivot)
                                      #   ⑥ S4 eval framework upgrade M3-M5 5/21-5/25
                                      #   ⑦ Autoloop M-Auto-1~5 5/26-6/05
                                      #   + commit count per stage
                                      #   + activity-day count per stage
                                      #   + 跳过 stages 标注: S1.5 / S2.5 / S5
```

**规则**:
1. **Read-only after first instantiation**: 首次落地后冻结;csagent 后续演化**不**回流
2. **Fold-back 方向**: 学到新洞见 → templates(live),**不**回流到任何 example
3. **Snapshot 重建机制**: 显著过期(用户判断)→ 开 sub-sprint 整体重建新 snapshot(`examples/csagent-reference-2027-Q1/`),旧目录保留(Δ-4 intermediate 规则)
4. **两个等价 framing 都成立**:
   - "aidazi 是基于 csagent 抽取的框架" → 读 templates 时引用 examples 看"填空后长什么样"
   - "用 aidazi 框架审视 csagent" → 读 examples 检查 csagent 真实做法是否对得上 templates 推荐

**与 v2 §E 关系**: v2 §E 说 donor → aidazi → new project 单向;§L 把 donor 在 aidazi 中的镜像具体定下来,反向迁移仍禁止。

---

## §13 — Open questions(carry-forward)

### §13.1 — 5 pushbacks from latest turn(本轮新增)PENDING

**PB1 Δ-15 重签触发分级 PENDING**: Q1/Q2/Q6 core re-sign vs Q3/Q4/Q5 amendment-with-incremental-sign。当前 Δ-15 一刀切重签;用户提议按字段分级。

**PB2 Δ-16 自动 OBS 生成可能 spam PENDING**: 多 deferred 类目应聚合为单条 "agent-prereqs-incomplete" parent OBS,避免 7 类各开一条。

**PB3 Δ-16 gate 判据 tier-aware PENDING**: enterprise 正式签批 / startup 命名 owner+日期 / 实验仅存在;当前 Δ-16 未细分判据严格度。

**PB4 Δ-16 Type C "1-page demo brief" 最低字段 PENDING**: 目标用户 1 行 / 演示效果 1 行 / 不演示什么 1 行 / 现成 skill 清单指针 — 是否需要在 Δ-16 内嵌该最小骨架。

**PB5 Δ-15 Part C 对 Type C 简化 PENDING**: 不要 tool-vs-skill 决策树;Type C 只问"有没有现成的;有就用,没有拼 tool"。Part C 是否需要 profile-aware 拆分文档。

### §13.2 — Δ-15 PB1(Q6 boundary 30-50 题问卷)PENDING

**Status**: 用户本轮**未直接答复**。
**两选项**:
- (A) 出 30-50 题问卷
- (B) 出 schema + 由 Tech Lead 当场展开

**建议时机**: Δ-16 落地后、首例 Type A 试跑前由用户裁决,因首例试跑会暴露 schema 是否足够指引人类作答。

### §13.3 — Δ-3 在七 deltas 间的相对落点 PENDING

等 Δ-11 / Δ-14 / Δ-15 / Δ-16 全部稳定后梳理。

### §13.4 — Other first-trial-pending(carry-forward,~7-8 项)

**v2 §I 遗留**(carry from Δ-8):
- "Tech Lead Agent" 命名 — v3 维持(Δ-1 未触及);本归档已采用
- aidazi repo 初始化时机 — Δ-2/Δ-3 各出一版 draft 之后再 bootstrap repo
- Orchestrator: spec-only vs reference impl — v3 暂维持 spec-only
- Customer barrier-break events — Δ-2 D1 业务调研喂入,部分答复

**Δ-8 v3 新增**:
- Decision-catalog 范围(Δ-3): 8 项一次性 vs 先做 P0-必决子集 — **倾向**先做必决 3 项
- Runtime skeleton T1/T2 边界(Δ-6): phase 集合 T1-fixed 还是 T1-shape-only — **需要决断**
- Worked-example-instance 维护周期(Δ-7): 何时算"过期到需要重建 snapshot"
- Doc category 划分粒度(Δ-4): `intermediate` 是否再细分;细分回到 sprawl
- Discovery 与 decision catalog 耦合(Δ-2 ↔ Δ-3): greenfield 必按序;已有项目逆序补 discovery 允许但 discovery 输出物必须存在才能 close 任何 Module
- Context-budget 数字基线(Δ-5): `target_tokens` 默认值从何来 — 与 §L example 不构成推荐原则张力

**Δ-12/13/14 follow-up**:
- csagent 既有 docs A/B/C 归档拆分(下 §13.5)
- Δ-12 taxonomy 完整性(11 行是否漏)
- Δ-13 git-commit 启发式经验值(N=5~10、X≤20%、Y≥60%、≥3 sub-sprint)用 csagent 真实历史反向验证
- Δ-14 Type B 过门后是否真不需要 S3
- §L worked example 补丁(Δ-12/13/14 在 csagent-reference 中的具体取值示例)

**Δ-15/16 follow-up**:
- Δ-16 前置物模板形态: 空骨架模板 vs bulleted checklist
- Δ-14 ↔ Δ-16 必需集: Type B "SOP 定义"替代"BRD+PRD"映射,首例 Type B 实例可能暴露不够
- Δ-15 Part D 综合稿模板: industry-synthesis 最小骨架(2-3 家方案对比、综合维度、特化路径)
- Δ-16 OBS-id 与 prereq-deferred: 新增标签 `prereq-deferred` 是否在 Δ-9 议题表显式建模子类型

### §13.5 — csagent 既有 docs A/B/C 归档拆分(OBS framing fix) PENDING

**用户上轮提的 csagent docs A/B/C 问题**:
- 是否把 csagent 现有 `docs/foundational/` / `docs/current/` / `docs/proposals/` / `docs/runbooks/` 作为 Δ-12 taxonomy 反向验证样本
- 是否把现有结构作为 §L 中的 reference 写入
- separate scope; pending user 决策

### §13.6 — 4 aligns confirmed THIS TURN(applied to this archive)

1. **S1.5 / S2.5 / S5 命名 OK** — 已应用于 §9.6 / §9.11(d)
2. **Δ-17 = 独立 case-study doc**(NOT inline annotations)— 已应用为 §9.11
3. **Δ-17-B / Δ-17-C placeholders start empty; track-separate** — 已应用为 §9.12
4. **Cognitive-detour disclaimer MUST 写入 Δ-17** — 已应用为 §9.11(f)

---

## §14 — Δ index appendix

| Δ | 内容 1-line | Source pointer |
|---|---|---|
| **Δ-1** | 框架定调: 从"框架架子"到"项目全生命周期";v2/v3 边界变化 | `framework-plan-v3-delta.md` §Δ-1 |
| **Δ-2** | `process/domain-discovery-process.md`(T0)三维度问题集 D1/D2/D3 | `framework-plan-v3-delta.md` §Δ-2 |
| **Δ-3** | `process/tech-architecture-decision-catalog.md`(T0)8 项决策;**Decision #1 track 绑定 S2-required event** | `framework-plan-v3-delta.md` §Δ-3 + `v3-followup` Δ-14 修订 |
| **Δ-4** | Doc lifecycle 区分 `live` vs `intermediate`;强制 front-matter `doc_category` | `framework-plan-v3-delta.md` §Δ-4 |
| **Δ-5** | Constitution refine: context-passing sufficient AND efficient;`context_budget` front-matter | `framework-plan-v3-delta.md` §Δ-5 |
| **Δ-6** | Type A recommended runtime architecture skeleton(PORTABLE-SKELETON)intent gate + multi-phase pipeline | `framework-plan-v3-delta.md` §Δ-6 |
| **Δ-7** | §L Worked Example Instance pattern;`examples/csagent-reference/` 单向 read-only 镜像 | `framework-plan-v3-delta.md` §Δ-7 |
| **Δ-8** | §I 修订;v2 遗留 4 项 + v3 新增 6 项 open questions | `framework-plan-v3-delta.md` §Δ-8 |
| **Δ-9** | OBS / autoloop role-split;`process/post-deployment-iteration.md`;OBS ≠ R-item;两层 triage + optimization | inline THIS TURN |
| **Δ-10** | `process/doc-responsibility-matrix.md`(T0)8 字段(含 Δ-12 新增 `artifact_type`) | inline THIS TURN + `v3-followup` Δ-12 (e) |
| **Δ-11** | `process/capability-staging-roadmap.md`(T0)S0/S1/S2/S3 + Δ-17 新增 **S1.5/S2.5/S3.5/S5/S6**;反向触发表;Δ-13 软化 F 行 | inline THIS TURN + `v3-followup` Δ-13 (e) + Δ-17 §9.11(d) |
| **Δ-12** | `process/artifact-taxonomy.md`(T0)11 artifact + per-role 必读 + action_bank open/archive 拆分 + cheatsheet | `framework-plan-v3-followup-delta.md` §Δ-12 |
| **Δ-13** | Architecture-stable 软化 stage-stable heuristic;框架不提供脚本;动态过程免责 | `framework-plan-v3-followup-delta.md` §Δ-13 |
| **Δ-14** | Profile-aware maturity;Type B "S2-required event";Δ-14 修订 = 增 "S0 prerequisites" 列(Δ-15) | `framework-plan-v3-followup-delta.md` §Δ-14 + `v3-deltas-15-16` Δ-14 修订 |
| **Δ-15** | `process/agent-design-elicitation.md`(T0)Part A 6 必答 + human-signoff + Part B profile-aware + Part C Type A only + Part D profile-aware industry research | `framework-plan-v3-deltas-15-16.md` §Δ-15(全 4 修订)+ Q3 |
| **Δ-16** | `process/agent-creation-prerequisites.md`(T0)7 类前置 + profile-aware 必需集 + READY/DEFERRED/N/A gate + Δ-9 OBS 集成 | `framework-plan-v3-deltas-15-16.md` §Δ-16 |
| **Δ-17** | `process/common-detours-and-warnings-typeA.md`(T0;Type A only)4 类结构性弯路 P1-P4 + 3 新 stage(S1.5/S2.5/S5)+ cognitive-detour disclaimer | inline FULL DRAFT THIS TURN |
| **Δ-17-B** | `process/common-detours-and-warnings-typeB.md` EMPTY placeholder;待 hermes 首例 lifecycle 完成填充 | inline THIS TURN |
| **Δ-17-C** | `process/common-detours-and-warnings-typeC.md` EMPTY placeholder;待 fortunes 首例 lifecycle 完成填充 | inline THIS TURN |

---

**End of v3.2 archive.** 单文件冷启动。下一轮工作输入: aidazi standalone repo bootstrap(P0 phase per §7),以本归档作为 `aidazi/archive/2026-06-06-v3.2-snapshot.md` 入口。
