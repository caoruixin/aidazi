# aidazi(AI 搭子)—— 面向 LLM-first 软件交付的受治理多智能体框架

[English](README.md) | **中文**

**v5.0.0**(`loop-engine-v5`)· 2026 · 采用 [Apache 2.0](LICENSE) 许可证

**aidazi(AI 搭子)** ——“搭子”即一起做事的**搭档**。它是你的 **AI 交付搭档**:一个你**接入(vendor)进自己代码仓库**的受治理多智能体软件交付框架,而不是一个你去部署的服务或调用的 CLI。它为你备好一条 **5 角色链**(Research / Deliver / Dev / Code Reviewer / Acceptance)、一个人类 **Customer**、两个各自命名的**循环**(交付循环 + 战役循环)、一部**治理宪法**,以及配套的流程文档、模板、schema 与一套参考引擎——并且能架在你已经在用的任意 **Coding Agent** 之上协同运转。

> **想接入 AI 搭子?** 把 [`ONBOARDING.md`](ONBOARDING.md) 交给你的 Coding Agent(Claude Code / Codex / Cursor),它会带你走一遍交互式、幂等、非破坏、全程可审计的**一次性安装**,把框架装进你的代码库。

---

## 目录

1. [设计理念 —— what](#1-设计理念--what)
2. [总体设计与组成部分](#2-总体设计与组成部分)
3. [何时该用 —— why](#3-何时该用--why)
4. [如何适配到你的 domain](#4-如何适配到你的-domain)
5. [怎么落地 —— 接入流水线(how)](#5-怎么落地--接入流水线)
6. [常见问题 FAQ](#6-常见问题-faq)
7. [术语表](#7-术语表)
8. [迭代升级历程](#8-迭代升级历程)
9. [仓库结构](#9-仓库结构) · [版本策略](#10-版本策略) · [参与贡献](#11-参与贡献) · [许可证](#12-许可证)

---

## 1. 设计理念 —— what

一个统领全局的理念高居其上,其余所有设计都只为把它落地:

> **让 LLM 掌管“软”的语义判断,让确定性运行时掌管“硬”的内核级不变量;在两者之间立起五个有*真实*边界的角色,使二者永不相互渗漏——并由人类 Customer 作为最终权威。**

支撑它的几条核心原则:

- **接入,而非调用。** 不存在所谓“AI 搭子 运行时”——真正的运行时是*你项目自己的*运行时。AI 搭子 只是一棵文档树 + 模板 + schema + 一套参考引擎,被逐字接入,用来塑造*你如何构建*。接入方在自己的 `docs/current/` 里做特化,**从不**改动框架本身。
- **归属边界:谁决定什么。** **LLM 掌管**软判断(用户目标、意图与漂移、下一步动作、升级姿态、面向用户的措辞);**确定性运行时掌管**硬不变量(工具 schema、能力与权限边界、PII 与安全底线、grounding 底线、预算与超时、幂等、持久化、trace 与 eval 契约)。一份**禁令清单**把软判断挡在代码之外:语义判断不得用关键词 / 正则 / if-else,prompt 与 runtime 不得内嵌 eval 措辞,每个 agent 只保留单一抽象层。——*宪法 §1.3/§1.4/§1.7*
- **完整性 ⇄ 质量,出自分离的源头。** 由 Research **撰写** `closure_contract`(预期行为:正向形态 + 反模式 + 锚定短语),再由 Acceptance **据此裁决交付行为**——两个角色、两个源头,互不代笔。正是这份对称,才让裁决真正回答“我们是否构建了**对**的东西”。——*§3.4 不变量 #4*
- **Customer 是最终权威;agent 只提议,绝不自我授权。** 人类是一个**角色**,而非出错时的兜底。agent 起草,Customer 在关口**签字**,并掌管 9 个 MANDATORY_CHECKPOINT。任何角色都不给自己的产出打分;**Acceptance 在结构上被隔离**(不得由 Research / Deliver / Dev 派生),以免发布裁决偏向交付方。——*§3.1/§3.4/§1.7-C*
- **默认建议(advisory-by-default)。** Acceptance 依据真实的**执行证据**(而非阅读代码)运行并给出裁决,但 `pass` 只是**建议**,会停下来等人类。只有在一个极窄的显式组合下它才自动升为权威:`mode==auto` **且** 该类别的裁判已*校准* **且** `fully_autonomous_within_budget`。——*§1.7-C/§3.6*
- **治理内核是唯一规范源头,且 fail-closed。** `constitution.md` 是唯一权威文档;禁令清单、角色边界不变量、9 个 checkpoint、校准均属**硬性要求**——任何将其省略 / 清空 / 关闭 / 覆盖的 charter,都会在**启动时被直接拒绝**。接入方只能*增加*约束,绝不能削减。——*§7.0/§1.8*
- **冷启动加载纪律。** 每个新角色 / 会话只加载一组精简、恒加载的**内核**(`constitution-core.md` + `authoring-kernel.md` + `context_briefing.md`),把硬约束廉价地*投影*出来;完整宪法按需加载。这样护栏时刻在位,又不必在每次派生子进程时重付整份治理上下文的开销。

---

## 2. 总体设计与组成部分

AI 搭子 是一个分层的栈:人类在最上和最下,一个自然语言控制面在最前,一条五角色链居中,两个循环驱动它运转,治理内核与适配器层则托在下面。

```mermaid
flowchart TB
    H["👤 Customer(人类)—— 最终权威:在关口 / checkpoint 签字"]
    CP["Control Plane —— 自然语言指令面(负责路由请求)"]
    subgraph CHAIN["5 角色链 · 每个角色都在独立、全新的会话中运行"]
      direction LR
      R["Research<br/>→ closure_contract"] --> D["Deliver / Tech Lead<br/>→ 计划 + 里程碑"] --> DV["Dev<br/>→ 代码 + 测试"] --> CR["Code Reviewer<br/>(只读)→ findings"] --> A["Acceptance<br/>(只读)→ 裁决"]
    end
    subgraph LOOPS["两个循环(确定性外循环驱动 LLM 内循环)"]
      direction LR
      DL["交付循环 —— 单个里程碑"]
      CL["战役循环 —— 整个 backlog"]
    end
    GOV["🛡 治理内核 —— 宪法 · 禁令清单 · 9 checkpoint · 校准(fail-closed)"]
    ADP["适配器 —— 每个角色 harness × provider × model(claude_code / codex / mock)"]
    H --> CP --> CHAIN
    CHAIN --> LOOPS
    GOV -. 治理每个角色 .-> CHAIN
    ADP -. 支撑每个角色 .-> CHAIN
    LOOPS -. 只在人类关口暂停 .-> H
```

### 2.1 5 角色链 + Customer

所有角色都跑在**全新、隔离的会话**里,上下文**只经由仓库文档**传递,绝不走聊天记录。每个角色背后接哪个 Coding Agent 由 charter 决定——但*边界*是普适的、与后端无关。

| 节点 | 是什么 | 输入 → 输出 | 关口 |
|---|---|---|---|
| **Customer**(人类) | 最终权威,不是 agent | 读 brief / 验收报告 / checkpoint → 批准 / 驳回 / 指示 | Gate 1、Gate 2、全部 9 个 checkpoint |
| **Research** | 入口关;Acceptance 的对等方 | 目标 + 代码样本 + failure-briefs → `research-briefs/<id>.md`,承载 **`closure_contract`** | 撰写 Gate 1 要签之物 |
| **Deliver**(Tech Lead) | 规划、编排、收口;**从不写代码** | 已签 brief / gap / bad-case → 里程碑与 sprint 目标、compact prompt、收口裁决、战役计划 | — |
| **Dev** | 只管实现;**无 scope 权限** | 自包含的 `compact/<sprint>-dev-prompt.md`(绝不读 `eval/bad_cases/`)→ 代码 + 测试 + handoff | — |
| **Code Reviewer** | *“代码建得好不好?”* + 反硬编码内核;**只读** | dev diff + handoff → 裁决 `pass \| fix_required \| out_of_scope_review` | 代码侧关口 |
| **Acceptance** | *“我们建的是不是对的东西?”* 对照契约裁决;**只读**、派生隔离 | 已签 `closure_contract` + 执行证据 → 裁决 `pass \| fix_required \| needs_human` | Gate 2:发布 / 不发布 |

```mermaid
flowchart LR
    C0(["👤 Customer"]) -->|目标| R[Research]
    R -->|closure_contract| G1{{"Gate 1:签 brief"}}
    G1 --> D[Deliver:规划] --> DV[Dev:实现] --> CR[Code Reviewer]
    CR --> DC[Deliver:收口] --> A[Acceptance:对照契约裁决]
    A --> G2{{"Gate 2"}}
    G2 -->|pass 建议性| C1(["👤 Customer 签字 → 发布"])
    G2 -->|fix_required| D
```

两个关口彼此**独立**,因此:Reviewer 通过而 Acceptance 不通过,是有价值的信号(代码建得漂亮,却做错了东西);Reviewer 不通过而 Acceptance 通过,同样有价值(能跑,但很脆)。

### 2.2 两个循环(必须分开命名 —— §1.7-E)

AI 搭子 坚持把两个循环**分清楚**(把它们混为一谈本身就是治理违规):

- **交付循环**(Δ-18,*团队在交付*):围绕单个里程碑—— sub-sprint → Dev → Review → deliver-close → 里程碑收口 Acceptance → 人类签字。确定性的**外**循环,通过 JSON 裁决 + 文件系统状态 + checkpoint 文件,来驱动非确定的 LLM **内**工作。作为一种*模式*它是普适的;而它的自动化层则*取决于* `autonomy.level`——纯人工粘贴的接入方完全可以不用它。
- **战役循环**(P-B,*整个目标*):架在“单里程碑 Driver”(保持不变)之上的更高一层循环。它从一份**已签、有序的里程碑 backlog** 出发,端到端把整个目标推到完成(以终为始),在*每一个*里程碑收口都运行 Acceptance,并**只在人类权威关口暂停**。入口:`engine-kit/scheduling/run_loop.py --campaign`。
-(此外还有 **Auto Loop**——*产品 agent 自我改进*,仅限 Type A——它与交付循环彼此组合,但命名上必须分开。)

```mermaid
flowchart TB
    SB["📝 已签的里程碑 backlog —— campaign_plan_signoff(人类关口)"]
    subgraph CL["战役循环 —— 推动整个目标,只在人类关口暂停"]
      direction TB
      subgraph DL["交付循环 —— 单个里程碑"]
        SS["sub-sprint:Dev → Review → deliver-close"] --> AC["里程碑收口 Acceptance"] --> HS["👤 人类签字(Gate 2)"]
      end
      HS --> NEXT["自动推进 → 下一个里程碑"]
      NEXT -.-> DL
    end
    SB --> CL
```

### 2.3 支撑组件

- **Control Plane(控制面)** —— 新 Coding Agent 默认落入的会话:一个位于角色链**之前**的轻量自然语言指令面(不是第六个角色)。它把请求归入某个路由类别、记下一条 schema-valid 的 intent,再派发或恢复正确的角色 / runner。它**从不**替产物签字、写裁决,也从不绕过 checkpoint。
- **治理内核** —— `constitution.md`(唯一规范源头)在冷启动被投影成恒加载内核;charter 校验器会**拒绝任何 checkpoint 绕过,并直接拒绝启动**。
- **需求台账(Requirement Ledger)+ OW-M3** —— `docs/requirements-ledger.json`,一份持久、与入口渠道无关的“需求 → 处置”记录。每条需求的 **`surface`**(`user_facing` / `non_user_facing`)是一份输入契约:任何覆盖了 `user_facing` 需求的里程碑,其功能验收**必须**收敛为 **`browser_e2e`**(真实浏览器驱动的证据),否则签署直接被拒。它是增量、非侵入的:没有台账即休眠、逐字节一致。自 **v5** 起,onboarding 会**默认生成**一份带种子的台账,并由 Research 自动提议 `surface`——新接入方因此天然接通 Acceptance,人类只需在权威点上确认(**不新增任何运行时关口**)。
- **Quick-Fix 车道** —— 一条人类显式发起、**独立于循环**的车道,用于小的**非行为性**修复。它跑在所有循环*之外*(因此没有可跳过的 checkpoint),结果绝不自动应用(由人类 cherry-pick),遇到不受支持的 harness 则 fail-closed(`claude_code` + `codex` 受支持)。
- **适配器 / harness 抽象** —— 每个角色在 `charter.tooling.<role>` 里绑定一个 `harness × provider × model`;无论背后接的是哪个 agent,角色边界都保持不变。这正是 AI 搭子 **与 harness 无关**的根源。

---

## 3. 何时该用 —— why

当**正确性与“防漂移”比单纯的速度更重要**时,AI 搭子 的这点开销才值回票价:多步或跨会话的 agent 工作,“能跑”并不等于“对”,你需要持久可审计的产物,而且必须由人类牢牢握住“发布什么”的权力。

**先选你的 track**(它决定哪些模式现在就要、哪些可以延后):

| Track | 是什么 | 什么时候选它 | 例子 |
|---|---|---|---|
| **Type A** | 每轮自适应推理的 agent | CS agent / 助手——决策实时做出 | 退款政策聊天机器人 |
| **Type B** | 跑固定 SOP、每步带校验的 agent 化工作流 | 有验证关口的既定流水线 | 多轮文档评审循环 |
| **Type A+B** | 由 LLM 掌控顶层循环、其下驱动一个 SOP runner | 既要自适应控制、*又要*结构化执行 | 驱动工作流引擎的助手 |
| **Type C** | 可演示性优先于覆盖度的 demo / POC | 依托现成 skill 的展示 | 黑客松原型 |

**分类型看,接入 AI 搭子 各自能拿到什么:**

- **Type A** —— `closure_contract` + 已校准的 Acceptance,把“机器人感觉挺对”变成一份对照*已签预期行为契约*、凭执行证据而非感觉给出的**可度量**裁决;eval 金字塔 + `trace_check` DSL 让裁判本身可审计。
- **Type B** —— 逐步验证加里程碑收口 Acceptance,能拦住固定流水线悄悄漂移;战役循环把整条 SOP backlog 推到完成,同时在人类关口停下等确认;浏览器 E2E 验收更进一步,证明*用户旅程真的走得通*,而不只是“每一步都有返回值”。
- **Type A+B** —— 两循环纪律让“自我改进(纵向)”与“团队交付(横向)”不至于互相踩脚,各有各的关口与证据。
- **Type C** —— 最轻的接入:5 角色链 + 一份 `closure_contract` + 一次 Acceptance,不启用编排器,也能做出一个仍然信得过的 demo。

**一句话价值:** AI 搭子 把自主 agent 工作,从*你靠肉眼盯着的临时 prompting*,变成一条*有真实边界、有人类关口、以执行证据验收、并留下持久审计轨迹的受治理流水线*——让循环放心地跑,而不会悄悄跑偏。

---

## 4. 如何适配到你的 domain

AI 搭子 **感知 track、但与 domain 无关**:domain 由你提供,结构由框架提供;适配只发生在**你自己的** `docs/current/`,绝不动框架。

**业务特点 → 三份 domain 契约**(每个角色冷启动都会加载):

- `domain_taxonomy.md` —— 你的实体、用例与词汇,是所有角色共享的一套语言。
- `runtime_invariants.md` —— 你的 **Tier-0** 硬规则,也就是这个 domain 里不可协商的红线(例如*“资格判定必须是一次工具调用,绝不能让 LLM 猜”“不得出现跨客户 PII”“每一轮都要被记录”*)。它们构成归属边界里“运行时掌管”的那一侧。
- `eval_acceptance_bars.md` —— 你的 KPI 阈值 + 安全底线(例如*“资格准确率 ≥ 0.95、错误 containment ≤ 0.02”*)。它们构成常驻的验收底线。

**技术特点 → 两个务必分清的“栈”:**

- **实现栈(implementation stack)**(`docs/current/implementation-stack.md`,onboarding Step 4a)——*产品自身的*语言、框架、构建与测试工具、数据存储、部署目标。这是产品事实。
- **agent 执行栈(execution stack)**(`charter.yaml`,onboarding Step 5 Facet A)——*运行每个角色*的 `harness × provider × model`。你可以有意把角色摊到不同 provider 上(比如 Dev 用一家、Code Reviewer + Acceptance 用另一家),让评审 / 验收相对 Dev 真正跨 provider——从而不自我打分。

**几条使用注意:**

- **每一处偏离都要记录。** 当你偏离某个建议默认值时,在 `docs/current/adoption-state.md` 里把它标为 `divergent` 并附一句理由。但硬性要求(禁令清单、角色墙、checkpoint、校准)**不可**偏离——那是框架违规,不是定制。
- **硬编码的软判断,是 brownfield 接入里最大的摩擦源**——把当前埋在 `if/else`、正则里的语义判断找出来,挪到边界的 LLM 一侧。
- **不在注册表内的模型**会触发一条*非阻塞*校验警告——属正常提示,而非错误。
- **连接器默认拒绝**——只有当某个任务确实需要时,才给对应角色授予对应连接器。

---

## 5. 怎么落地 —— 接入流水线

### 5.1 onboarding 向导(一次性安装,Step 0–9)

把 [`ONBOARDING.md`](ONBOARDING.md) 交给你的 Coding Agent,它会一次一个决策地带你走完这套交互式、幂等、非破坏、可审计的安装:

| 步骤 | 决策 | 产出 |
|---|---|---|
| 0 / 0a | bootstrap 台账 + 确认 cwd = 接入方仓库 | `adoption-state.md` + `onboarding-record.md` |
| 1–2 | greenfield 还是 brownfield(+ 盘点) | 接入形态 |
| 3 | 接入 track(A / B / C / A+B) | `track:` |
| 4 | 意图契约(目标 / 标准 / proof_of_done)→ 首份 research brief,人类签字(**Gate 1**) | `research-briefs/RB-001-*.md` |
| **4a** | 接入方**实现栈**快照 | `docs/current/implementation-stack.md` |
| **4b** | **需求台账** —— *默认开启*(v5):agent 提议 `surface` + 置信度,Customer 用签署来确认 | `docs/requirements-ledger.json` |
| 5 | 角色配置 —— 3 facet × 5 角色(执行 × skill × 连接器) | charter `tooling.*` |
| 6 | 生成接入方产物(`AGENTS.md`、`charter.yaml`、`docs/current/*`、接入 `engine-kit/` + `schemas/` + `skills/`) | 接入方文件树 |
| 7 | autonomy + checkpoint 姿态 | charter `autonomy.*` |
| 8 | **校验 —— 绿灯关口**(`charter_validator.py` exit 0) | 绿灯结果 |
| 9 | 交接给 [`FIRST-LOOP.md`](FIRST-LOOP.md) | 循环开始 |

随后,一个**全新会话**被喂入 `FIRST-LOOP.md`,驱动 `engine-kit/scheduling/run_loop.py`:冷启动并重新确认意图 → 重新校验 charter → 选模式(需要先拆解就 `full_chain_guided`,否则 `delivery_only`)→ **先离线 mock 跑一遍**(零模型调用,验证状态轨迹 + 审计哈希链)→ **真实运行**(`--allow-real`)。

### 5.2 一条具体流水线(脱敏后的真实接入)

*下面是一次真实的 Type B 接入,已泛化为一个中性的“评审工作台(review-workbench)”产品——一个对抗式文档评审循环:一个 Proposer 不断增强草稿,一个 Critic 不断攻击它,迭代到收敛裁决。你的 domain 和栈会有所不同。*

1. **track = Type B,greenfield。** 它的价值是一条带收敛关口的、编排式的多步 SOP——而非自我改进的 Type A 流水线。greenfield 全量继承宪法。
2. **onboarding Step 0–9** 逐决策走完:Step 4 产出一份人类**已签**的 research brief(`confirmed_by_human: true` 即 Gate 1),其 `closure_contract` 固定了这套循环的预期行为;Step 4a 记录产品自身技术栈;(更新后、默认开启的)Step 4b 台账为每条需求分类 `surface`。
3. **三份 domain 契约**写在 `docs/current/`:`domain_taxonomy.md`(草稿 / 反对 / 修订 / 轮次 / 裁决 / 转录)、`runtime_invariants.md`(Tier-0:每轮都被记录;恰好产出一个裁决;循环有 N 轮上界;最终稿由*人类*签署;入口校验 fail-closed)、`eval_acceptance_bars.md`(常驻质量底线)。
4. **角色跨 provider 摊开**以求独立:Dev 用一家 harness / provider;**Code Reviewer + Acceptance 只读、且用另一家 provider**,让评审 / 验收相对 Dev 跨 provider(不自我打分)。每处偏离都在 `adoption-state.md` 附理由记录在案。
5. **autonomy = human_on_the_loop**;强制 checkpoint 全部触发;循环隔离 = 每个循环一条新分支;预算上限用可计数的代理量表达。
6. **首个循环 → 交付 / 验收循环。** 每个 sub-sprint:Dev 依据一份精简的 `compact/<sprint>-dev-prompt.md` 实现(顺带自测运行中的应用)→ Code Reviewer 做只读静态评审(修复轮次有上界)→ 里程碑收口时,Acceptance 对照已签 `closure_contract` 裁决交付行为并给出结论 → 人类签字。对 user-facing 里程碑,人类关口之前还要跑一次**浏览器 E2E 证据运行**(happy 路径 + 失败路径,持久状态需与 UI 一致);由 Deliver 协调,Acceptance 拥有那份只读的权威裁决。
7. **产出的产物** —— `charter.yaml`(mission · autonomy/scope · budget · 5 个角色绑定 · 审计台账目录)、已签 brief、三份 domain 契约、需求台账,以及 `runs/<id>/` 下每次运行的输出(转录、多版本草稿、裁决、状态、逐次调用日志),并配一条哈希链审计台账。

### 5.3 如果只做三件事

1. 写一份 **`closure_contract`**,并对照它跑一次独立的 **Acceptance**。
2. 采用 **5 角色链**——正是这些边界,才让 Acceptance 的裁决值得信。
3. 写好**三份 domain 契约**——它们给每个角色一份可靠、共享的 domain 上下文。

---

## 6. 常见问题 FAQ

### AI 搭子 落在哪一层:一座金字塔

AI coding 里大家最关心的几个概念—— **Coding Agent**、**Prompt Engineering**、**Harness Engineering**、**Loop Engineering** ——并不是相互竞争,而是层层叠起来的。**Coding Agent** 是最底层的原始能力;三门工程学科在越来越高的“海拔”上驾驭它;而 **AI 搭子** 稳坐塔尖——正是它把最高一层学科,变成了一套你敢放手让它自己跑、又不会悄悄跑偏的受治理框架。

```
                     ┌───────────────────────────┐
                     │          aidazi           │   受治理的多智能体交付:
                     │        (受治理交付)       │   宪法 · 5 角色 · 人类关口 · Acceptance
                   ┌─┴───────────────────────────┴─┐
                   │       Loop Engineering        │   替你 prompt agent 的那套系统:
                   │                               │   scheduling · worktree · maker/checker
                 ┌─┴───────────────────────────────┴─┐
                 │      Harness Engineering          │   单次 agent 运行:
                 │                                   │   tools · context window · sandbox · model
               ┌─┴───────────────────────────────────┴─┐
               │        Prompt Engineering             │   单次请求:
               │                                       │   一条 prompt 的措辞
               └───────────────────────────────────────┘
                        ▲ 海拔越高 · 作用范围越广 · 治理越强
```

*(Coding Agent 本身不是某一层——它是每一层都在驾驭的那个对象。)*

### 一览:在几个关键维度上横向对比

| 维度 | **Coding Agent**(直接用) | **Harness Engineering** | **Loop Engineering** | **AI 搭子** |
|---|---|---|---|---|
| **关注单位** | 一个会话、一次改动 | 单次 agent 运行 | 一段时间里的许多次运行 | 里程碑与战役 |
| **优化什么** | 这一次回复 | 一个 agent *怎么*执行(tools/context/sandbox) | 那套*持续 prompt*的系统 | *交付纪律*本身 |
| **谁在 prompt agent** | 你,一轮一轮 | 你,装备更好 | 你搭的那套循环 | 受治理的角色链 + runner |
| **怎么验证** | 你肉眼看 | 仍旧临时 | maker/checker(建议性) | **Acceptance 对照已签 `closure_contract`,凭执行证据裁决** |
| **人类的角色** | 每一轮都在环里 | 单次运行的操作者 | 搭好循环、然后退到一旁 | 一个**角色**,握着循环*无法自我收口*的关口 |
| **持久产物** | 聊天回滚 | 运行配置 | 一份 `STATE.md` | brief · handoff · findings · 验收报告 · 台账 · 哈希链审计 |
| **与 AI 搭子 的关系** | AI 搭子 把它当作某角色背后的 agent 来编排 | AI 搭子 架在其上、与 harness 无关 | AI 搭子 把它产品化并补上治理 | —— |

### AI 搭子 vs. Coding Agent

- **区别。** 一个 Coding Agent 是单会话、临时的 prompt→改代码循环:同一个上下文又规划、又写码、还(隐式地)给自己打分;验证全凭你肉眼;产物是聊天回滚。AI 搭子 在其上补齐:一部**宪法 + 禁令清单**(界定哪些决策属模型、哪些属运行时)、**五道角色墙、各在全新隔离会话**里(*谁都不给自己打分*)、循环*无法自我收口*的**人类关口**,以及**持久、可版本化的产物**(而非易逝的 prompting)。
- **联系。** AI 搭子 并不取代 Coding Agent——它**编排**它:Coding Agent 就是**某个角色背后的 agent**(`charter.tooling.<role>.agent_kind`)。
- **一句话:** *Coding Agent 是干活的工人,AI 搭子 是围着它的那支受治理团队、那份契约、那道验收关口。*

### AI 搭子 vs. Harness Engineering

- **区别。** Harness Engineering 装备的是*单次 agent 运行*——它的 tools、context window、sandbox、provider/model 管道;它优化的是*一个 agent 怎么执行*,比循环低一层。
- **联系。** AI 搭子 通过**适配器抽象**架在 harness **之上**,且**与 harness 无关**:每个角色绑定一个 `harness × provider × model`(`claude_code`、`codex`、`mock`……),无论背后是谁,角色边界都不变,参考引擎的外循环只用 read/write/shell。
- **一句话:** *Harness Engineering 让一个 agent 跑得好;AI 搭子 决定“一个跑得好的 agent 被允许做什么、由谁签字放行”。*

### AI 搭子 vs. Loop Engineering

- **区别。** Loop Engineering(Cherny、Osmani、Steinberger)是这样一门实践:*去设计那套替你 prompt agent 的系统*,而不是一轮一轮亲自 prompt——由 scheduling、worktree、skill、连接器、maker/checker 子 agent、持久 `STATE.md` 这些积木手工拼起来。它坦率地承认危险(无人值守的循环会犯无人值守的错),却把补救交给读者的自律。
- **联系。** **AI 搭子 本身就是一门产品化的 Loop Engineering 纪律**——几乎一一对应:scheduling → Δ-18/战役编排器;worktree → scope envelope + charter;skill → 角色-skill 模型;连接器 → 每角色 charter 工具;maker/checker → 5 角色链且 Acceptance 结构隔离;持久状态 → handoff + 台账 + 证据。凡是经典留作*建议*之处,AI 搭子 都把它做成*结构*。
- **一句话:** *Loop Engineering 点出了机会;AI 搭子 补上了那部宪法、那些 checkpoint、那组边界不变量——让循环不会悄悄跑偏。*

### 其他常见问题

- **必须用编排器 / 自动化吗?** 不必。5 角色链完全可以纯手工(人工粘贴)跑。编排器 + 战役循环*取决于* `autonomy.level`;纯人工粘贴的接入也是一种完整、合法的用法。
- **支持哪些 Coding Agent / harness?** AI 搭子 通过适配器与 harness 无关;目前 `claude_code` 与 `codex` 为 `supported`(有真实运行证据留档),`mock` 是离线默认,不受支持的 harness 一律 fail-closed。你为每个角色各绑一个。
- **接入 AI 搭子 会不会把我锁死在某一家 LLM provider?** 不会——每个角色各设自己的 `harness × provider × model`,而且鼓励你把角色摊到不同 provider(比如 Dev 一家、Code Reviewer + Acceptance 另一家),让评审 / 验收相对 Dev 真正跨 provider。
- **agent 会不会在我不知情时就把东西发出去?** 只有在一个极窄的显式组合下才会(`mode==auto` **且** 该类别裁判已*校准* **且** `fully_autonomous_within_budget`)。否则 Acceptance 只是**建议**,由人类签字;未校准的裁判会自动降级为 human-on-the-loop。
- **只能用在 greenfield 吗?** 不是。brownfield 接入讲究“对账而非推倒重来”——先从 **Acceptance 关口**入手(价值最高、扰动最小),再逐步接入其余角色,并把每处偏离记进 `adoption-state.md`。
- **框架更新怎么进到我的仓库?** 不会自动进。AI 搭子 是**接入(copy 进来)**的,你按自己的节奏消费更新;承重的经验则通过**回折(fold-back)**协议双向流动。
- **什么时候 AI 搭子 属于杀鸡用牛刀?** 对一个用完即弃的 demo、或“能跑就行”的一次性脚本,轻量路径(5 角色链 + 一份 `closure_contract` + 一次 Acceptance,不上编排器),甚至只用 Acceptance 关口,就是合适的剂量。它的开销,是在正确性与防漂移真正要紧时才回本的。
- **我已经有自己的 eval / CI 了怎么办?** AI 搭子 只是*规定*了一套 eval 金字塔 + 6 原语的 `trace_check` DSL,具体由你落地;而 Acceptance 依**执行证据**裁决,所以它是给你的 CI 做补充,而非替代。

### 新手阅读顺序

1. 本文 → 2. `docs/adoption-overview.md` → 3. `docs/two-loops-explainer.md` → 4. `governance/constitution.md`(权威核心)→ 5. `governance/doc_governance.md` → 6. `governance/context_briefing.md` → 7. 分 track 指南(`docs/greenfield-guide.md` / `docs/brownfield-guide.md`)→ 8. `docs/directory-taxonomy.md` → 9. 5 张角色卡 → 10. 按需加载 `process/` 下的 Δ 文档。

---

## 7. 术语表

| 术语 | 一句话释义 |
|---|---|
| **Research Agent** | 入口关;撰写 `closure_contract`;Acceptance 的对等方 |
| **Deliver Agent**(Tech Lead) | 规划、编排、收口、拆解里程碑 / sub-sprint;从不写代码 |
| **Dev Agent** | 依自包含的 compact prompt 实现;无 scope 权限;绝不读 eval bad-case 集 |
| **Code Reviewer Agent** | 只读的代码侧关口:*“代码建得好不好?”* + 反硬编码内核 |
| **Acceptance Agent** | 只读的结果关口:对照契约*“是不是建了对的东西?”*,凭执行证据裁决;派生隔离 |
| **Customer** | 人类;最终权威;签 Gate 1 / Gate 2,掌管 checkpoint |
| **closure_contract** | brief 里的强制段落(正向形态 + 反模式 + 锚定短语),定义里程碑 scope;Acceptance 据此裁决 |
| **campaign_plan_signoff** | 战役层的人类关口:Customer 签署有序的里程碑 backlog |
| **covers_req_ids** | 已签里程碑所交付的需求 id 列表——唯一权威、可写的“需求→里程碑”覆盖源 |
| **surface** | 需求的 `user_facing \| non_user_facing` 类别;决定里程碑是否必须跑浏览器 E2E 验收(OW-M3)的输入契约 |
| **requirement ledger(需求台账)** | `docs/requirements-ledger.json`;持久、与入口无关的“需求→处置”记录(Δ-19);缺席即增量休眠 |
| **customer_disposition** | 需求的 `pending\|accepted\|deferred\|…`;已决值仅 Customer 可写(agent 只能种下 `pending`) |
| **milestone / sub-sprint** | 由 Acceptance 关口收口的交付单元 / 其内部原子的 dev→review→close 单元(每里程碑 3–5 个) |
| **MANDATORY_CHECKPOINT** | 9 个人类权威不可协商的点;charter 可增不可绕——否则校验器拒绝启动 |
| **acceptance_input_hash / LOAD-CLOSURE** | 绑定每一项影响裁决的 Acceptance 输入的摘要;建议 / 撰写类字段会被投影剔除——不留未绑定输入 |
| **kernel / constitution-core** | 冷启动时持有的、宪法硬约束的恒加载精简投影 |
| **control plane** | 默认的轻量自然语言指令会话,把请求路由到角色链 / runner;不是第六个角色 |
| **Two Loops** | 交付循环(团队交付)与 Auto Loop(agent 自我改进)之间的命名区分 |
| **delivery loop / campaign loop** | 单里程碑的团队交付(Δ-18) / 架在 Driver 之上、只在人类关口暂停的多里程碑外循环 |
| **Quick-Fix 车道** | 人类显式、独立于循环的小型非行为修复车道;结果绝不自动应用;遇不支持的 harness 则 fail-closed |
| **adapter / harness** | 每角色 `harness × provider × model` 绑定,角色边界在其下保持不变 |
| **calibration(校准)** | 每(裁判模型 × 项目)一次的关口(一致率 ≥ 0.9、翻转率 ≤ 0.1),Acceptance 自动发布前必过,否则自动降级 |
| **fold-back(回折)** | 双向协议:接入方向上报 lesson,维护者把承重模式向下折进发布 |
| **cold-start(冷启动)** | 全新隔离会话的初始受治理加载(内核 + 角色卡 + 自包含 prompt) |
| **browser-E2E 验收(OW-M3)** | user-facing 里程碑的强制功能验收类别:编排器驱动运行中的应用、提交哈希锚定的证据、Acceptance 只读裁决 |
| **signed scope hash / F1** | 已签的解析后 scope 快照 + `signed_scope_hash`;签署后任一编辑都会令其 `stale`,强制重签 |

---

## 8. 迭代升级历程

tag 目前有 `loop-engine-v1`、`-v4`、`-v5`;`v2`/`v3` 从未打 tag(那两段弧落在 v1→v4 区间里)。v1 之后的每一段能力弧,在落地前都过了 Codex 门禁(REVISE→APPROVE)。

| 里程碑 | Tag | 落地的核心能力 |
|---|---|---|
| **起源 —— 多智能体链** | *(未打 tag)* | 与 domain 无关的治理 + 角色卡链(deliver / dev / review / research)+ 反硬编码纪律;随后立即折入 Acceptance Agent 与流程文档。 |
| **硬内核 + 引擎 MVP** | *(未打 tag)* | 宪法 / 硬内核底座、charter 校验器(能力门、连接器默认拒绝)、Loop Controller + Loop Memory + Loop Ingress,以及 agent 驱动的 onboarding 向导。 |
| **v2 循环引擎** | **`loop-engine-v1`** | 战役循环引擎 + **Quick-Fix 车道**(独立于循环的维护、多 harness 适配器)、Default-Full harness 接线、onboarding Step 4a + 前置 roadmap、有界 review runner、强化的逐派生审计。 |
| **自主交付** | *(v1 区间)* | 默认开启的建议性 Acceptance(P-A)、带 fail-closed 恢复的战役 runner + 每里程碑 Acceptance(P-B)、浏览器 E2E 验收关口(P-C)。 |
| **scope 覆盖 + 需求台账** | *(v1→v4 区间)* | “已签 backlog vs 已交付”的 scope 覆盖报告 + 统一**需求台账**(Δ-19)可加性骨干 + 控制面 roadmap schema。 |
| **上下文 / token 优化(WP-0→WP-9)** | **`loop-engine-v4`** | 度量基线;带 LOAD-CLOSURE 不变量的 **constitution-core / authoring / acceptance 内核**;任务范围化的 Close 冷启动;分层有界的 Loop-Memory lesson;建议性上下文预算 lint。**冷启动通用地板降约 36%,close/acceptance 最高降 57%。** |
| **Track-2 gap 跟进 + 四轨集成** | *(v4→v5 区间)* | §1.7-F 对未覆盖需求的 gap 驱动自动路由;任务感知的动态 skill 挂载;human-on-the-loop 模板默认;合并为一次集成。 |
| **Track-2 新鲜度加固** | *(v4→v5 区间)* | 通用 F1 新鲜度门 + 持久授权覆盖层——签署后的授权变更会阻断执行,而正常运行时演进无需重签。 |
| **OW-M3 —— 强制浏览器 E2E** | *(v5)* | 把浏览器 E2E 验收从建议性升格为**需求驱动的强制**关口,并对需求台账做 fail-closed 探测。 |
| **OW-AUTO —— 验收自动提议 & 初始化默认开启** | **`loop-engine-v5`** | 为新接入方自动激活 Acceptance/OW-M3:建议性 `surface` 提议接线、初始化即种下的默认开启需求台账、置信度确认 UX——**不新增任何运行时关口**。 |

---

## 9. 仓库结构

```
aidazi/
├── README.md · README.zh-CN.md    —— 本文件(EN / 中文)
├── AGENTS.md                       —— 消费侧根模板(harness 接线)
├── ONBOARDING.md · FIRST-LOOP.md · QUICK-FIX.md   —— 三份面向人类的 runbook
├── LICENSE · NOTICE                —— Apache 2.0
├── governance/                     —— Layer A(恒加载内核 + 按需权威)
│   ├── constitution-core.md · authoring-kernel.md · context_briefing.md   —— 恒加载
│   ├── constitution.md · doc_governance.md · acceptance-kernel.md         —— 按需权威
├── process/                        —— Layer B(约 25 个编号 Δ 模式,按需由角色加载)
│   ├── delivery-loop.md · campaign-loop.md · control-plane-routing.md
│   ├── requirement-ledger.md · customer-checkpoints.md · fold-back-protocol.md · …
├── role-cards/                     —— 5 张 agent 角色卡
├── templates/                      —— 接入方可复制模板(charter、compact prompt、台账)
├── schemas/                        —— 裁决 / 计划 / 台账形态的 JSON schema(+ compact/ 投影)
├── engine-kit/                     —— 可复制的参考引擎(orchestrator、adapters、validators、scheduling、tools)
├── skills/                         —— 打包的角色 skill(Agent Skills / SKILL.md 标准)
├── modules/                        —— 模块规格(m-evaluation、m-trace、m-autoloop、m-memory)
├── docs/                           —— 应用指南(adoption-overview、two-loops、分 track 指南、taxonomy、licensing)
├── examples/                       —— 已做示范实例(minimal-greenfield + build 触发的参考)
├── maintainer/ · lessons/ · tools/ · archive/   —— 维护者工具 · 回折收件箱 · 脚本 · 设计历史
```

## 10. 版本策略

- `v5.0.0`(`loop-engine-v5`)—— 当前稳定发布。
- `vX.0.0` —— 大版本(Δ 删除、角色链变更、破坏性 front-matter 形态)。
- `vX.Y.0` —— 小版本(向后兼容的 Δ 新增 / 扩展)。
- `vX.Y.Z` —— 补丁(错别字 / 文档澄清)。

接入方按自己的节奏消费(不自动更新)。框架 → 接入方方向见 `process/fold-back-protocol.md` §1.2。

## 11. 参与贡献

这是一个框架,所以“贡献”意味着:**采用它**(在真实项目上试用;哪里不契合,就用 `templates/lessons-learned-template.md` 上报一条 lesson),以及**回折(fold-back)**(在回折节奏上,由维护者把承重的模式折进 Δ 修订)。**不算**贡献的是:在回折之外对框架文档提周期中 PR(宪法 §8),或对 `examples/<ref>/` 在首次快照后再作编辑(按 Δ-7 只读)。

## 12. 许可证

采用 **Apache License 2.0** —— 见 [`LICENSE`](LICENSE) 与 [`NOTICE`](NOTICE),说明文档见 [`docs/licensing.md`](docs/licensing.md)。你可以在 Apache 2.0 条款下使用、修改并再分发 aidazi(包括把它接入你自己的仓库);该许可证授予显式的专利许可,并要求你保留 `NOTICE` 与署名。把框架接入你的接入方仓库,正是它预期中的用法。
