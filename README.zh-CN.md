# aidazi —— 面向 LLM-first 软件交付的多智能体框架

[English](README.md) | **中文**

**v4.0.0** —— 2026

aidazi 是一个以多智能体团队交付软件的框架:由 LLM 负责"软"的语义判断,由确定性运行时(runtime)掌管"硬"的内核级不变量。它定义了一条 5 角色链(Research / Deliver / Dev / Code Reviewer / Acceptance)+ 一个人类 Customer + 配套的治理、流程文档、模板与 schema,使其能够协同运转。

## 框架总览(自顶向下)

aidazi 是自顶向下读的。塔尖是一个统领性的核心想法;其下的一切都只为把它落地。

**统领性的核心想法**

> 让 LLM 掌管"软"的语义判断;让确定性运行时掌管"硬"的内核级不变量;并在二者之间立起五个有*真实*边界的角色,使两者永不相互渗漏。

其余一切都是为这一句话搭的脚手架。它由五根支柱支撑。

### 支柱 1 —— 归属边界:*谁决定什么*

LLM 的判断与运行时的保证之间那条线是被显式划定的,而非听天由命。

- **LLM 掌管**(软):用户目标、意图 / 话题假设、漂移检测、下一步动作选择、升级姿态、面向客户的措辞。
- **Runtime 掌管**(硬):工具 schema、能力 / 权限边界、PII 与安全底线、grounding 底线、预算 / 超时、幂等性、持久化、trace 与 eval 契约。
- 一份**禁止清单**把语义判断挡在代码之外:软判断不得用关键词 / 正则 / if-else 匹配、不得把评估短语硬编码进 prompt 或运行时、每个智能体只允许单一抽象层。
- 出处:`governance/constitution.md` §1。

### 支柱 2 —— 5 角色链:*真实的墙,不是标签*

| 角色 | 职责 | 门(Gate) |
|---|---|---|
| **Research** | 把守入口;撰写 `closure_contract` | Gate 1:已签署的 brief |
| **Deliver**(Tech Lead) | 规划、编排、收尾 —— 绝不写代码 | — |
| **Dev** | 实现;无范围裁定权 | — |
| **Code Reviewer** | "代码造得好不好?" + 反硬编码内核 | 代码侧门 |
| **Acceptance** | "我们造对了吗?" 对照契约判定 | Gate 2:发布 / 不发布 |
| **Customer**(人类) | 签 Gate 1、读 Gate 2、掌管强制检查点 | 两道门 |

承重的不变量:**没有任何角色给自己的活打分。** Acceptance 在*结构上被隔离*——不得从 Research、Deliver 或 Dev 派生(spawn)——这样"发布与否"的判定就无法偏向产出这份活的那个团队。出处:`role-cards/`、`governance/constitution.md` §3。

### 支柱 3 —— 两个分开命名的回路:*自我改进 vs 团队交付*

- **Auto Loop**(概念 1,仅 Type A):产品智能体改进*它自己*——prompt、技能、阈值。`modules/m-autoloop.md`。
- **Delivery Loop**(概念 2,所有 track):多智能体*团队*收敛到客户所要之物。`process/delivery-loop.md`(Δ-18)。
- 二者可组合(纵向深度 × 横向流动),且在采用者文档中绝不可混为一谈。

### 支柱 4 —— 流程层:*约 25 个可移植的 Δ 模式*

每个 Δ 都是一个小而可移植的模式,由需要它的角色按需加载:领域发现(Δ-2)、技术决策目录(Δ-3)、运行时骨架 + 6 原语 trace DSL(Δ-6)、上线后 / OBS 分诊(Δ-9)、按 track 的成熟度(Δ-14)、Delivery Loop 规范(Δ-18),以及其余。出处:`process/`。

### 支柱 5 —— 证据脊柱:*可度量的校验*

- 一座 **4 层评估金字塔**:`tier1_smoke`(确定性)→ `tier2_scenario`(语义评审)→ `tier3_target_set`(契约锚定)→ `tier4_shadow`(留出集泛化)。
- 一套 **6 原语 `trace_check` DSL**——`tool_call_present`、`tool_call_order`、`slot_collected`、`session_flag`、`any_of`、`all_of`——其文法*在结构上拒绝*关键词 / 消息内容匹配。
- **F5 证据**:Acceptance 依据执行产物来判定,绝不靠代码审阅。出处:`modules/m-evaluation.md`。

**如何顺着金字塔往下读:** 先读始终加载的 **Layer A**(`governance/`——宪法、文档治理、上下文简报),再按角色按需拉取 **Layer B**(`process/` 的 Δ 文档),把鲜活的**状态账本**留在你自己的仓库里,并把每个 sprint 的**prompt 工件**冻结在 `compact/` 下。完整文档树索引见 `governance/constitution.md` §11。

## aidazi 是什么

- 一部**宪法**(`governance/constitution.md`),界定 LLM 与 Runtime 的归属边界 + 一份禁止清单(语义判断不得用关键词/正则匹配、不得把评估短语硬编码进代码,等等)。
- 一条带显式边界不变量的**5 角色链**——没有任何角色给自己打分;Acceptance 在结构上与 Deliver/Dev 隔离,以避免偏见回路。
- 一个由约 25 个编号 Δ 组成的**流程层**(领域发现、决策目录、运行时骨架、OBS 分诊、坏样本生命周期等)——每个 Δ 都是一个小而可移植的流程模式。
- **两个被明确命名区分的回路**:**Auto Loop**(概念 1;Type A 智能体自我改进)与 **Delivery Loop**(概念 2;Δ-18 多智能体团队交付)。二者可组合,不冲突。
- 一个**编排器模式**(Δ-18 Delivery Loop)——可选的状态机 + spawn 函数 + checkpoint 收件箱 + scope 信封 + F5 证据 + 校准门。想要自动化的采用者使用它;纯人工粘贴的采用者保留链条而不要自动化。
- 一个**角色-技能模型**(`process/role-skill-model.md`)——角色是问责边界;行业能力包(Agent Skills / SKILL.md 标准、编码智能体的 subagent 库)挂载在角色**内部**,作为角色技能或角色内 fan-out,绝不作为新的链条角色。`skills/` 下随附一个样例化的打包技能。
- 一个**双向回流**(采用者 → 框架经验教训;框架 → 采用者发布)机制,使框架从真实的采用者经验中演化,而非由委员会拍板。

## aidazi 不是什么

- 不是运行时——没有所谓"aidazi 服务器"供你部署。运行时是**你自己项目**的运行时;aidazi 只塑造你如何构建它。
- 不是单一工具——背后的编码智能体(Claude Code / Codex / 其他)可按角色、按 charter 配置。
- 不对领域持立场——框架是 track-aware 的(Type A AI 智能体 / Type B 智能体工作流 / Type C demo / Type A+B 混合),但领域无关。
- 不是一个 LLM 评估框架——但它规定了一座 4 层评估金字塔 + 6 原语的 trace_check DSL(`modules/m-evaluation.md`),供采用者实例化。

## 如何把 aidazi 应用到你的代码库

理解"如何采用"最快的路径,就是那一份随框架附带、已填好的可工作示例:**`examples/minimal-greenfield/`**——一个完整、最小的 Type A 实例,名为 **Acme Returns Bot**(一个客服智能体,负责对照政策回答*"这笔订单能退款吗?"*)。下面每一步都对应该示例里的一个真实文件。

### 第 0 步 —— 选定你的 track

| Track | 是什么 | 何时选它 |
|---|---|---|
| **Type A** | 每一轮自适应推理的智能体 | 客服智能体、助手——决策当场做出 |
| **Type B** | 跑固定 SOP、带逐步校验的智能体工作流 | 带验证门的既定流水线 |
| **Type A+B** | 在 SOP 执行器之上、由 LLM 控制的顶层回路 | 既要自适应控制*又要*结构化执行 |
| **Type C** | 看重可演示性、覆盖度其次的 demo / POC | 倚重现成技能的展示型项目 |

你的 track 决定哪些 Δ 模式当下必要、哪些可延后(`process/profile-aware-maturity.md`,Δ-14)。Acme Returns Bot 属于 Type A。

### Greenfield(全新项目)—— 复制示例,替换领域

1. **把 `examples/minimal-greenfield/` 复制为你的起始目录树**,编辑 `AGENTS.md` §1:`project_name`、`adopter_track`、`framework_version`。每个新会话都先读 `AGENTS.md`;默认是轻量 Control Plane 入口,显式角色会话再加载完整治理链与对应 role card。
2. **以 Research 角色跑澄清(elicitation)**(`process/agent-design-elicitation.md`,Δ-15)→ 写一份像 `docs/research-briefs/RB-001-*.md` 的研究 brief。其核心是 **`closure_contract`**:一个*正向形态* + 一个*反模式* + 一组*锚定语句*(示例性语言,**而非**关键词匹配器)。Customer 签字——这就是 **Gate 1**。
3. **撰写三份领域契约**,置于 `docs/current/` 下(它们是宪法的领域专属对应物,每次冷启动都会加载):
   - `domain_taxonomy.md` —— 实体、用例、词汇表。
   - `runtime_invariants.md` —— 你的 Tier-0 硬规则(Acme 的:资格判定是一次工具调用、绝不靠 LLM 猜;不跨客户泄露 PII;处理需幂等)。
   - `eval_acceptance_bars.md` —— KPI 阈值 + 安全底线(Acme 的:资格准确率 ≥ 0.95、错误兜底 ≤ 0.02)。
4. **以 Deliver 角色做规划**:`docs/milestone_objective.md` + `docs/sprint_objective.md`,并初始化 `docs/action_bank.md`(鲜活待办)+ `docs/10-handoff.md`(冷启动载体)。
5. **构建 → 评审**:Dev 依据 `compact/` 下一份冻结的、自包含的 prompt 实现(Dev 绝不读取 `eval/bad_cases/`——污染规则);Code Reviewer 把守不变量 + 反硬编码内核。
6. **里程碑收尾时验收(Gate 2)**:Customer 在一个*全新*会话里派生 Acceptance Agent;它跑坏样本套件(`eval/bad_cases/`),对照已签署的 `closure_contract` 判定交付行为,并把裁决写入 `docs/acceptance-reports/`。若为 `fix_required`,由一个 human-confirm 检查点决定退回路线。
7. **(可选)用编排器自动化**(`templates/mission-charter.yaml`,Δ-18)——仅当你想要机器驱动的派发时才用。纯人工粘贴 + 5 角色链,本身就是一种完整、有效的采用方式。

### Brownfield(既有项目)—— 调和,而非推倒重来

1. **先盘点,什么都别改。** 记下你的 track、你现有的治理 / 评估文档,以及——最关键的——*语义判断当前住在哪里*(由 LLM 掌管,还是被硬编码)。被硬编码的软判断预示着最大的摩擦。
2. **从 Acceptance 门开始**——价值最高、扰动最小的第一步。为当前里程碑写一份 `closure_contract`,在收尾时于全新会话派生 Acceptance(绝不从 Deliver / Dev 派生),读它的裁决。它回答你现有流程答不了的问题:*"代码很干净,可我们造对了吗?"*
3. **其余逐步采用**——Code Reviewer(反硬编码内核)→ Acceptance → Research(已签 brief)→ Deliver → Dev(自包含 compact,日常改动最大的一项)。
4. **记录每一处偏离**于 `docs/current/adoption-state.md`(取自 `templates/adoption-state-template.md`):把每个 Δ 标为 `at-spec` / `partial` / `divergent` / `not-applicable`,每处偏离附一句理由。

### 如果你只做三件事

1. 写一份 **`closure_contract`**,并对照它跑一次独立的 **Acceptance**。
2. 采用 **5 角色链**——正是这些边界让 Acceptance 的裁决可信。
3. 撰写**三份领域契约**——它们给每个角色一份可靠、共享的领域上下文。

### 其余示例(构建触发型参考)

- **`examples/csagent-reference/`** —— Type A 全生命周期参考;当某个 Type A 采用者需要深度走查时填充。在此之前,minimal-greenfield 就是鲜活的 Type A 参考。
- **`examples/hermes-reference/`** —— Type A+B 混合(Delivery Loop *与* 带 SOP 层的 Auto Loop);构建触发。
- **`examples/fortunes-reference-placeholder/`** —— Type C demo 占位;等待第一个完成完整生命周期的 Type C 项目。

## aidazi vs. Loop Engineering(回路工程)

### 回路工程是什么

"Loop engineering"(回路工程)是一个新兴说法——由 Claude Code 周边的实践者(Boris Cherny、Addy Osmani、Peter Steinberger)提出——指的是人们与编码智能体协作方式上的一次转变:**别再逐轮地给智能体写 prompt,去设计那个替你写 prompt 的系统。** Cherny 的原话是*"我不再 prompt Claude 了,我让一堆回路在跑、由它们去 prompt Claude。"* Osmani 将其概括为*"把'那个去 prompt 智能体的人'换掉——换成你设计的系统。"* Steinberger 则把这道命令说得很直白:*"你应该去设计那些 prompt 你的智能体的回路。"*

它高于此前两个概念一个层级:

- **Prompt engineering(提示工程)** 优化的是单次请求。
- **Harness engineering(框架工程)** 装备的是单次智能体运行——它的工具、上下文、沙箱。
- **Loop engineering(回路工程)** 设计的是那个*按节奏不断戳智能体的系统*——发现工作、委派、校验、迭代,且逐轮回路里没有人。

相关论述收敛到一组反复出现的构件:

| # | 回路工程构件 | 作用 |
|---|---|---|
| 1 | **自动化 / 调度**——"心跳" | 周期性的发现 + 分诊,无需人来启动 |
| 2 | **Worktrees(工作树)** | 隔离的检出目录,让并行智能体互不冲突 |
| 3 | **Skills(技能,`SKILL.md`)** | 把约定外置,使智能体每次运行不必从头重新推导上下文 |
| 4 | **Plugins & connectors(插件与连接器,MCP)** | 让回路去**执行**(开 PR、更新工单),而不只是给建议 |
| 5 | **Sub-agents(子智能体,maker / checker)** | 第二个智能体校验第一个——杜绝自评 |
| + | **持久状态(`STATE.md`)** | 一条跨周期、能挺过上下文重置的记忆脊柱 |

### 收敛:aidazi 走到了同一套架构上

aidazi 是独立设计的——它的血统是多智能体软件*交付*,而非编码智能体的工具链——却落到了同一组构件上,因为二者回答的是同一个问题:*如何让自主的智能体工作跑起来又不漂移?* 二者的映射近乎一一对应:

| 回路工程构件 | aidazi 机制 |
|---|---|
| 自动化 / 调度 | **Δ-18 Delivery Loop** 编排器(状态机 + spawn 函数 + checkpoint 收件箱)与 **Auto Loop**(`modules/m-autoloop.md`) |
| Worktrees / 隔离 | 按任务的 **scope 信封** + 按角色的 **charter** + 角色内 fan-out(`process/role-skill-model.md`) |
| Skills | **角色-技能模型** + `skills/` 下的打包角色技能(同一套 Agent Skills / `SKILL.md` 标准) |
| Plugins & connectors | 背后的编码智能体**按角色、按 charter** 可配置(`charter.tooling.<role>.agent_kind`);待补工具在 `tools/` 追踪 |
| Sub-agents(maker / checker) | **5 角色链**,且 **Acceptance 在结构上与 Deliver/Dev 隔离**——以制度化方式确保*没有角色给自己的活打分* |
| 持久状态 | **handoff 载体** + `adoption-state`、`action_bank` 账本 + F5 证据产物 |

一句话:**回路工程把它描述成一种自发涌现的实践,aidazi 则把它规定成一套被治理的框架。**

### aidazi 更进一步:把告诫做成结构

回路工程文献最引人注目之处,在于它对自身带来的风险毫不讳言——而又把补救留给了读者的自律。aidazi 的独到贡献,正是把这份纪律做成*结构性的*、而非*劝诫式的*。把该文献的三条告诫,映射到 aidazi 的结构性回答:

| 回路工程的告诫 | aidazi 的结构性回答 |
|---|---|
| *"无人值守的回路会犯无人值守的错误"*——校验仍归人 | **Customer** 是一个*角色*,不是兜底;**Gate 1**(已签 brief)与 **Gate 2**(验收)是回路**无法自行关闭**的检查点(`process/customer-checkpoints.md`) |
| *"理解力欠债在加速"*——你交付了自己没写的代码 | **`closure_contract`** 在前期固定意图行为;**Acceptance** 依据 **F5 执行证据**(而非代码审阅)对照它判定交付行为——于是"它跑通了"永不能替代"它做对了" |
| *"那个让你舒服的姿势,恰恰是危险的姿势"*——自动化诱发被动 | **宪法** + **禁止清单**编码了*哪些*判断永不可被自动化成关键词/正则/if-else;而且在 Acceptance 被允许自主运行之前,必须先通过一道**校准门** |

在这三条之外,aidazi 还补上了回路工程论述尚未命名的东西:

- **是一部宪法,而非一种感觉。** `governance/constitution.md` 固定了 LLM 与 Runtime 的归属边界。回路工程说"保留你的判断力";aidazi 则编码了*哪些*判断归模型、哪些归确定性内核。
- **两个回路,分开命名。** 那些论述把"the loop"混为一谈;aidazi 用明确的命名纪律(`docs/two-loops-explainer.md`)把 **Auto Loop**(智能体自我改进)与 **Delivery Loop**(团队交付)分开,使其相互组合而非彼此碰撞。
- **校验本身可被度量。** 在 maker/checker 拆分之外,**4 层评估金字塔** + **6 原语 `trace_check` DSL**(`modules/m-evaluation.md`)让"那个 checker"也可被审计——且该 DSL 的文法在结构上禁掉了关键词匹配这条捷径。
- **框架会回流。** 一个双向协议(`process/fold-back-protocol.md`)让框架从真实采用者的经验教训中演化,而不是靠一次次零散的回路微调。

### 二者的关系 —— 不同海拔,而非竞争者

- **回路工程**是*洞见*:杠杆点从 prompt 移到了"去 prompt 的那个系统"。
- **aidazi**是该系统的*运行纪律*:让一个自主回路保持诚实的那些角色、边界、检查点与治理。

实操层面的读法:

- **采用了回路工程、感到漂移?** aidazi 正是对*"好——那我现在怎么把它管住?"*的一个具体回答。从 Acceptance 门开始(见上文*如何应用*)。
- **已经在跑 aidazi?** 回路工程的论述是一种独立印证:链条、maker/checker 拆分、技能模型,正是行业在自行走向的同一处——同时它也是好的工具点子来源(worktrees、调度、连接器),把它们挂载进角色**内部**,绝不作为新的链条角色(`process/role-skill-model.md`)。

> **要点:** 回路工程命名了机会——*把"写 prompt 的人"换成你自己设计的系统*。而 aidazi 补上了回路工程文献声称你需要、却没真正给出的那部分:让回路不至于悄悄走偏的宪法、人类检查点与边界不变量。

**延伸阅读:** Addy Osmani,[*Loop Engineering*](https://addyosmani.com/blog/loop-engineering/) · The New Stack,[*Loop Engineering*](https://thenewstack.io/loop-engineering/) · Cobus Greyling,[*Loop Engineering*](https://cobusgreyling.substack.com/p/loop-engineering)。

## 阅读顺序

如果你是 aidazi 新手,请按此顺序阅读:

1. **本文件**(你正在这里)。
2. `docs/adoption-overview.md` —— 心智模型:aidazi 决定什么、不决定什么。
3. `docs/two-loops-explainer.md` —— Auto Loop 与 Delivery Loop 的命名纪律(宪法 §1.7-E)。
4. `governance/constitution.md` —— 始终加载的核心。
5. `governance/doc_governance.md` —— front-matter schema + 分层模型 + 编辑规则。
6. `governance/context_briefing.md` —— 冷启动阅读纪律 + Context Pack Prompt。
7. 按 track 的采用指南:
   - 全新项目(Greenfield):`docs/greenfield-guide.md`。
   - 既有项目(Brownfield):`docs/brownfield-guide.md`。
8. `docs/directory-taxonomy.md` —— 快速查"这块内容该放哪儿?"
9. `role-cards/` 下的 5 张角色卡 —— 按需每个会话采用一张。
10. `process/` 下的 Δ 文档 —— 按角色按需加载。

框架完整的文档树详见 `governance/constitution.md` §11。

## 仓库结构

```
aidazi/
├── README.md                    — this file
├── AGENTS.md                    — consumer-side template
├── governance/                  — Layer A (always-load)
│   ├── constitution.md
│   ├── doc_governance.md
│   └── context_briefing.md
├── process/                     — Layer B (on-demand by role)
│   ├── delivery-loop.md         — Δ-18 (Concept 2)
│   ├── customer-checkpoints.md  — human-side gate catalog
│   ├── self-governance.md       — bloat prevention mechanics
│   ├── fold-back-protocol.md    — adopter ↔ framework cadence
│   └── ... (~22 more Δ + promoted process docs)
├── role-cards/                  — 5 agent role cards
│   ├── research-agent.md
│   ├── deliver-agent.md
│   ├── dev-agent.md
│   ├── code-reviewer-agent.md
│   └── acceptance-agent.md
├── templates/                   — adopter-copyable templates
│   ├── mission-charter.yaml
│   ├── anti-hardcode-review-kernel.md
│   ├── compact-dev-prompt.md
│   ├── compact-review-prompt.md
│   ├── compact-acceptance-prompt.md
│   ├── compact-research-brief.md
│   ├── compact-codex-rebuttal-prompt.md
│   ├── deliver-close-taxonomy.md
│   ├── adoption-state-template.md
│   ├── lessons-learned-template.md
│   ├── sprint-objective.md
│   ├── milestone-objective.md
│   └── handoff-template.md
├── skills/                      — packaged role skills (Agent Skills standard; SKILL.md)
│   └── anti-hardcode-review-kernel/  — exemplar (normative source stays in templates/)
├── schemas/                     — JSON schemas for verdict shapes
│   ├── mission-charter.schema.json
│   ├── review-verdict.schema.json
│   ├── deliver-close-verdict.schema.json
│   ├── deliver-plan-fix.schema.json
│   ├── acceptance-verdict.schema.json
│   ├── research-brief.schema.json
│   ├── case-spec.schema.json
│   ├── adoption-state.schema.json
│   └── sprint_stanza.schema.json
├── modules/                     — module specs
│   ├── m-evaluation.md          — 4-tier pyramid + 6-primitive DSL
│   ├── m-trace.md               — portable trace shape
│   └── m-autoloop.md            — Concept 1 (Auto Loop)
├── docs/                        — Application Guide
│   ├── adoption-overview.md
│   ├── two-loops-explainer.md
│   ├── directory-taxonomy.md
│   ├── friction-playbook.md
│   ├── greenfield-guide.md
│   ├── brownfield-guide.md
│   ├── domain-adaptation.md
│   ├── industry-mapping.md
│   └── application-funnel.md
├── examples/                    — worked instances (read-only after snapshot)
│   ├── minimal-greenfield/      — working consumer template
│   ├── csagent-reference/       — Type A donor snapshot (build-trigger)
│   ├── hermes-reference/        — Type A+B hybrid snapshot (build-trigger)
│   └── fortunes-reference-placeholder/  — Type C placeholder
├── lessons/                     — adopter → framework fold-back inbox (.gitkeep until first lesson)
├── tools/                       — referenced-but-deferred scripts (OQ-V4-009 tracker)
└── archive/                     — v3.2 + v4 design-history snapshots (read-only)
```

## 版本管理

框架发布带版本号的 release:

- `v4.0.0` —— 首个稳定的 v4 release。
- `v4.0.x` —— 补丁 release(错别字修订、文档澄清)。
- `v4.x.0` —— 小版本 release(Δ 新增或扩展;向后兼容)。
- `v5.0.0` —— 大版本 release(Δ 删除、角色链变更、破坏性 front-matter 形态变更)。

采用者按自己的节奏消费(无自动更新)。框架 → 采用者方向见 `process/fold-back-protocol.md` §1.2。

## 如何参与(Contributing)

这是一个框架。参与意味着:

- **采用它**:在真实项目上试用框架;当某处不契合你的语境时,提交经验教训(`templates/lessons-learned-template.md`)。
- **回流(Folding back)**:在框架的 fold-back 子 sprint 节奏(见 `process/fold-back-protocol.md` §2)上,框架维护者审阅经验教训,并把承重的模式纳入 Δ 修订。
- **可工作的示例**:当你完成一个里程碑或完整生命周期时,框架维护者可能邀请你贡献一份快照到 `examples/`。

不属于参与的行为:
- 未经 fold-back 而直接对框架文档发起周期中的 pull request。宪法 §8 治理-编辑-纪律适用。
- 在首次快照之后修改 `examples/<ref>/`——按 Δ-7 为只读。

## 许可证

见 LICENSE 文件(若存在)。

---

全文完。
