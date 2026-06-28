---
title: Requirement Ledger (Phase 1) — session handoff / transferable context
date: 2026-06-24
branch: v2-loop-engine
purpose: 让新 session 直接接手"统一需求账本"的实施，无需重读旧对话
canonical_spec: archive/2026-06-23-requirement-ledger-design.md   # 详细设计的唯一真相源（733 行，Codex-APPROVED）
---

# 上下文包：统一 Requirement Ledger（Phase 1）

> 这是一个**可迁移上下文包**。设计细节的唯一真相源是
> `archive/2026-06-23-requirement-ledger-design.md`（已提交 `7707b9a`，Codex gpt-5.5
> xhigh 5 轮 APPROVE）。本文件只保留"会影响后续决策"的精炼信息；实施前请先读那份 spec，
> 尤其 §5（穷尽式 impact inventory）和 §3.3.1 / §3.5.1。

---

## 一、背景

- **项目**：`/Users/caoruixin/projects/aidazi` —— 一个多角色"交付环"引擎框架（Delivery Loop /
  Campaign Loop）。被多个 adopter 以 git submodule 方式引用（airplat、venture-strategy 等）。
- **触发问题**（用户原始诉求）：从一份 PRD（或任意需求输入）出发，如何保证 milestone 拆解与
  PRD 匹配；在交付若干 milestone（含中途新增）后，如何清晰知道"交付内容 vs 最初 PRD 的范围差距、
  哪些功能模块没实现"；并能方便地选择是否继续剩余 milestone。
- **调查结论**：框架原本**缺这层能力**——没有 intake 无关的统一需求记录；没有
  requirement→milestone→delivery 追溯；状态词汇只有生命周期（pending/in_progress/done/halted/
  failed），表达不了用户的"跳过/不做/挪后/改"；记录分散在三条**互不交汇**的轴：
  契约轴（proposals→research-briefs/closure_contract）、执行轴（campaign-plan→campaign-state→
  scope_report）、backlog 轴（action_bank R-item/OBS，且 milestone close 时被 sweep 到 archive）。
- **用户的关键重构**（这就是 Phase 1 的方向）：不管哪种渠道提供需求
  （PRD / 用户提的问题 / 一个需求点 / 成熟的 bad-case / acceptance-gap），都应**归一化成同一种
  持久、可在一处查看的记录**；**不要按来源分别维护账本**（那样过于复杂）。账本要能看到：完成情况、
  顺序、用户是否要做、以及用户直接跳过/修改/不做的处置。

---

## 二、目标（spec §1.2，G1–G5）

- **G1** 一个持久、intake 无关的 **Requirement Ledger**：任何渠道的需求都归一化成一种记录（REQ-NNN）。
- **G2** 每项的 **`customer_disposition`**（Customer 权限）表达真实选择 + 顺序/优先级。
- **G3** **可追溯**：signed milestone 的 `covers_req_ids` ⇒ 推导出每条 REQ 的交付状态（无回写）。
- **G4** **一处可见**：`scope_report` 投影每条 REQ 的覆盖；杀手特性 = **`uncovered_requirements`**
  （没有进任何 milestone 的需求 = 真正的"相对 PRD 的缺口"）。
- **G5** **需求粒度的"continue menu"**，集中在一处。

**Non-goals（本阶段不做）**：自动分解器；LLM 设定 disposition；改写 closure_contract；
跨 campaign 汇总 / 并行 runner（Phase 2+）。

---

## 三、已确认事实（实施时必须遵守的现实约束）

### 3.1 角色分工（用户心智模型已验证正确）
- **Research Agent** = 入口闸：产出 `docs/research-briefs/<id>.md` 的 `closure_contract`
  （positive_shape/anti_pattern/anchor_phrases，**行为契约**，Gate-1 冻结，"什么/为什么"）。
- **Deliver Agent（DL = Tech Lead）** = 产出**技术方案 + 把需求拆成 milestone → 3–5 sub-sprint**
  （"怎么做"）；并拥有 campaign 层的有序 milestone backlog。**不写代码**。
- **Acceptance Agent** = 判定交付行为是否满足 closure_contract。

### 3.2 关键代码 / 文件（实施落点）
- `engine-kit/orchestrator/scope_report.py` — **Phase-0 已落地**的纯只读投影器
  （`compute_coverage` / `summary_line` / `render_text` / `freeze_baseline` / `load_baseline` / CLI）。
  **Phase-1 在此扩展 REQ 维度投影**。已修正：按 `topological_order` 投影（非 raw 顺序）；drift
  覆盖被整体删除的 milestone units。
- `engine-kit/orchestrator/campaign.py` — Campaign runner。`CampaignState`（to_dict/from_dict）、
  `topological_order`、`derive_milestone_context`（解析 milestone 的 acceptance class）、
  `campaign_plan_signoff` honor 路径、`_DISPATCH_TABLE`/`interpret_dispatch`、
  `KNOWN_CHECKPOINTS`/`classify_checkpoint`（fail-closed 清单）、`_validate_or_raise`（schema 校验）。
- `engine-kit/scheduling/run_loop.py` — CLI。`run_campaign_entry`（含 guarded scope_coverage 块）、
  `print_campaign_result`（打印 `CAMPAIGN_STATUS=` / 附加 `SCOPE_COVERAGE=`）、
  `make_campaign_decision_resolver`、exit codes（0 done/10 paused/11 ended/2 invalid）。
- schemas：`campaign-plan.schema.json`、`campaign-state.schema.json`、`campaign-decision.schema.json`、
  `research-brief.schema.json`（**注意：`additionalProperties: false`**，第 17/53/94 行）、`mission-charter.schema.json`。
- 文档：`process/campaign-loop.md`（§3.4 fail-closed 清单、§3.7 functional_acceptance 继承、§5.1 scope-report、
  §6 signoff）、`process/artifact-taxonomy.md`（"14 artifacts"，§8 说"加第 15 个是 substantive change"）、
  `governance/constitution.md`（§1.3/§1.7/§3.4#4/§3.5/§7.0）、`role-cards/{research,deliver,acceptance}-agent.md`。

### 3.3 必须遵守的不变量（Codex 反复校验过的红线）
- **Constitution §3.4 #4**：closure_contract **Gate-1 冻结、不可变**；改动走
  `research_contract_revision`（Gate-1 重签）。**设计必须保持冻结**——曾有"从 ledger 实时派生
  closure_contract"的方案，**已否决**（会破 #4）。
- **§1.3 / §1.7**：`customer_disposition` 只能由 Customer 设定，**绝不能由 LLM/正则推断**。
- **Acceptance 角色边界**（`acceptance-agent.md` §9）：只能写 `docs/acceptance-reports/` 和
  `docs/checkpoints/`——**Acceptance 不能写 ledger**。所以 `delivery_status` 必须是 scope_report 的
  纯推导，**没有引擎/Acceptance 回写**。
- **fail-closed checkpoint inventory**（`test_campaign.py::TestCheckpointInventoryFailClosed`）：
  任何新 checkpoint id 必须加入 `campaign.py` 的分类集合，否则 build 失败。**本设计不新增 checkpoint**。
- **机器输出契约**：`CAMPAIGN_STATUS=` 必须**逐字节不变**；新行只能附加（`SCOPE_COVERAGE=` /
  未来 `REQUIREMENT_COVERAGE=`），且仅在有效 ledger 存在时才发。

### 3.4 调查中发现的**既有框架缺陷**（被本设计 surface 出来）
- **`campaign_plan_signoff` 没有完整性绑定**——它只是 `signed_by_human: true`
  （`process/campaign-loop.md` §6）。即：plan 签字后仍可被编辑（删 milestone、改未来的
  `covers_req_ids`）而保持"已签"。这是"signed scope 静默收窄"的真正漏洞，是 F1 要解决的问题
  （见决策记录 D7）。**F1 本质是 campaign_plan_signoff 的加固，可作为独立硬化先行落地。**

---

## 四、决策记录（5 轮 Codex 评审后定稿的设计要点）

> 编号对应 spec。每条都是"已定 + 为什么"。

- **D1 一种记录 = requirement item（REQ-NNN）**：字段 `title/statement/kind(business|technical|
  constraint)/source{channel,ref}/priority/order/customer_disposition/gap_type/relates_to_req_ids/
  elaboration/supersedes·superseded_by/history`。**`kind=technical|constraint` 解决了"技术要求无家可归"。**
- **D2 index, not duplicate**：ledger **只引用** brief/bad-case（单向 `elaboration`），**绝不复制**
  closure_contract 文本。`research-brief` 不改（它是 additionalProperties:false）。
- **D3 两个分离字段（核心修正，Round-1）**：
  - `customer_disposition`（**Customer 唯一权限**）：`pending|accepted|deferred|skipped|dropped|modified`。
  - `delivery_status`（**纯推导**，scope_report 投影，**无回写**）：`not_started|in_progress|delivered|waived`。
- **D4 单一权威映射（Round-2 B3）**：REQ→milestone 映射只存在 signed `campaign-plan` 的
  **`covers_req_ids`**（unique、`^REQ-` patterned、Phase 1 **至多一个 milestone 覆盖一条 REQ**）。
  ledger 不存可写 `covers[]`，覆盖率靠推导。
- **D5 intake 防重复计数（Round-2 B4）**：acceptance-gap / 成熟 bad-case 默认
  `gap_type=unmet_existing` + `relates_to_req_ids`（指向已存在 REQ）；只有 Customer/Research 确认
  `new_scope` 才新建 REQ。
- **D6 不新增 checkpoint（Round-2 B5）**：signed-scope 变更走**既有**路由
  （`research_contract_revision` / plan 重签）；unsigned backlog 改 disposition = 直接编辑 ledger。
- **D7 F1 = 签名纪元（plan signature epoch，Round-2→5 反复加固，最终形态）**：
  plan 增 `signoff` 块 `{signed_by_human, signer, signed_at, charter_ref, charter_hash,
  scope_envelope, signed_scope_hash}`。**`scope_envelope` 存"签字时的 RESOLVED 范围快照"**——
  每个 milestone 的 `{id,objective,covers_req_ids,subsprint_sequence,depends_on,
  resolved_functional_acceptance:{mode,source},acceptance_bar}` + 顶层 `goal`。
  - **存 resolved（非 literal）`functional_acceptance`**：因为它缺省时会**继承 charter 默认**
    （§3.7 / `derive_milestone_context`），charter 改默认会改 resolved class——必须能被 hash 捕获（G1）。
  - **hash spec（单一对象）**：`signed_scope_hash = sha256(canonical_json(H))`，
    `H = {version:"v1", campaign_id, goal, charter_ref, charter_hash, milestones:[...]}`；
    canonical JSON = UTF-8 / 键排序 / 无多余空白 / 空数组归一（absent ≡ `[]`）。
  - runner 在 load 时重算 live resolved hash，**仅当 == 存的 hash 才认"signed"**；不匹配 ⇒
    **stale ⇒ 重新 pause 在 `campaign_plan_signoff` 要求重签**。
  - **stale 时**：scope_report 渲染**存的 snapshot**为"signed (STALE)"，prior coverage 可重建（G4）；
    stale scope 视为 **stale-signed/blocked**（**不是 "unsigned"**），不可用于把 REQ 移出视图。
- **D8 delivery 终态表（Round-3 G3，§3.5.1）**：`delivered` ≠ "cursor 越过"。runner 在每个
  milestone close 时把终态 stamp 进 campaign-state 新字段 `milestone_outcomes[]`。映射：
  - Acceptance pass（authoritative，或 advisory pass + `advisory_acceptance_pass_signoff` ship）⇒ `delivered`
  - `acceptance_fix_required`+`confirm:no` ⇒ `waived`(reason=fix_required_ship)
  - `needs_human`→`acceptance_surface_approve`→`approve_ship` ⇒ `waived`(reason=surface_approve)
  - **Acceptance OFF** 终态 close ⇒ `waived`(reason=acceptance_off)
  - 终态 `review_out_of_scope`→`accept_and_advance` ⇒ `waived`(reason=out_of_scope_advance)
  - **`waived` = 没有 Acceptance pass 就交付的统称（带 reason），永不算 delivered。**
- **D9 冲突报告（Round-3 G4 / Round-2 B1 / G2）**：对**绑定到 fresh-signed scope** 的 REQ，
  其 `dropped/skipped/deferred/modified` disposition 是 **`invalid_signed_disposition`** 冲突，
  REQ 仍**保留在** remaining/uncovered 视图直到重签。Acceptance 优先规则：ledger disposition
  **永不**压制 signed closure_contract 条款（冲突 ⇒ halt/重签）。
- **D10（§4 六个决策，全部 Codex 确认 hold）**：
  - §4.A closure_contract 冻结（拒绝实时派生）。
  - §4.B ledger 加载 = **by-role**（Research/Deliver/Acceptance/Customer），**不是** always-load
    （避免动 constitution always-load 链）。
  - §4.C 格式 = **JSON 为准 + scope_report 渲染人读视图**；Customer 编辑需要 edit-helper 保 history。
  - §4.D ledger 直接编辑**仅限 unsigned backlog**；signed 范围变更走重签（依赖 D7 才成立）。
  - §4.E disposition = Customer-only（HARD requirement，加进 `self-governance.md` §7.0）。
  - §4.F 作为**新的 Δ**（如 Δ-19）+ 新 `process/requirement-ledger.md` + adoption-state 行
    （比"扩展 Δ-12"更合适）。

---

## 五、当前任务 / 进度（git 实况）

分支 **`v2-loop-engine`**，工作树干净（仅 `.cursorindexingignore` / `.specstory/` 未跟踪，无关）。

- **Phase-0 已提交 `ba3f7c7`**：`scope_report.py`（只读覆盖投影）+ run_loop guarded 接线
  + `SCOPE_COVERAGE=` 附加行 + 测试 + `campaign-loop.md` §5.1。
  Codex xhigh **2 轮 REVISE→APPROVE**（round-1 抓到 2 个真 bug：cursor 用 raw 顺序而非
  `topological_order`；drift 漏掉被整体删除的 milestone units——均已修 + 4 个回归测试）。
  全套 `python3.12 -m pytest engine-kit` = **865 passed, 2 skipped**。
- **Phase-1 设计 spec 已提交 `7707b9a`**：`archive/2026-06-23-requirement-ledger-design.md`
  （status=approved-design, rev5+nb）。Codex xhigh **5 轮 REVISE×4→APPROVE**（零 blocking、
  零 inventory 遗漏、§4 六决策全 hold）。**design-only，ledger 的引擎代码尚未写。**
- **两个提交都 NOT pushed。**

---

## 六、下一步（按推荐次序）

1. **（待用户拍板）push** `v2-loop-engine` 到 GitHub `origin`（`ba3f7c7`+`7707b9a`）。
   —— 上一个 session 结束时用户只说"commit"未说"push"，**push 需用户明确指令**。
2. **Phase 1a — 只读模型（最低风险，先做）**：
   - 新 `schemas/requirement-ledger.schema.json` + `templates/requirements-ledger.template.json`。
   - `campaign-plan.schema.json` 加可选 `milestones[].covers_req_ids`。
   - campaign-state 加 `milestone_outcomes[]`（D8）；runner 在 close 时 stamp。
   - `scope_report.py` 扩展：REQ 维度投影 + 推导 `delivery_status`（终态表）+ `uncovered_requirements`
     + 附加 `REQUIREMENT_COVERAGE=` 行（仅当 ledger 有效）。
   - 配套测试。**Codex 门评审。**
3. **Phase 1b — disposition + F1 签名完整性 + 治理（load-bearing）**：`customer_disposition` +
   Customer ledger-edit（仅 unsigned）+ history + D5 intake + **F1 签名纪元（D7，是 unsigned/signed
   划分成立的前提）** + D9 冲突报告 + 治理/process/role-card/template 文档（artifact #15、新 Δ）。
   —— **F1 可作为独立硬化先行落地。**
4. **Phase 1c — 收尾**：Acceptance 优先规则写进 `compact-acceptance-prompt.md`、README/onboarding/example。
5. **adopter 迁移**：airplat（campaign 中途）、venture-strategy（M1–M4 已 close）回填 ledger；
   pre-F1 plan（无 snapshot）首次跑会要求**恰好一次重签**（一次性迁移，正常非回归）。

**穷尽式 impact inventory 在 spec §5**（涉及 schemas / engine / validators / tests / governance /
process / role-cards / templates / examples / onboarding / README / audit / adopter 迁移，
Codex 确认无遗漏）——实施前逐项对照。

---

## 七、注意事项（会影响后续答案的硬约束）

- **提交规范**：身份 `Rex1028 <caoruixin@163.com>`（已是 git config）；只推 GitHub `origin`
  （gitee 已弃）；commit message 结尾 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`；
  **commit/push 只在用户明确要求时做**；不在默认分支直接提交（当前 `v2-loop-engine` 是 feature 分支，OK）。
- **治理边界**：本变更是 substantive framework change（新 artifact #15 + 新 schema + 触 constitution）。
  按 fold-back stance：**agent 绝不擅自改 constitution**；spec §5.6 的 constitution 编辑是**提案**，由作者应用。
- **Codex 验证门**：framework 改动用 **Codex gpt-5.5 xhigh、headless、后台**评审。工具 =
  `engine-kit/tools/review_runner.py`（硬超时 + pgid kill + 有界 attempts）。
  调用样例（已验证可用，codex 0.134.0）：
  ```
  python3.12 engine-kit/tools/review_runner.py --timeout 2400 --inactivity-warn 300 \
    --attempts 2 --mandatory --prompt-file <prompt.md> --capture-dir <dir> \
    -- codex exec --json -o <dir>/verdict.txt -m gpt-5.5 \
       -c model_reasoning_effort="xhigh" -s read-only --skip-git-repo-check -C <repo>
  ```
  **坑**：后台 codex xhigh 单轮 ~270–1260s，且在**别的 Bash 调用里 `ps` 看不到**（独立命名空间）——
  **不要因为"看起来死了"就重启**，等约 25 分钟；`-o verdict.txt` 偶发不写，则从 `<dir>/stdout.txt`
  的 JSONL 里抽 final agent_message。
- **测试**：用 **`python3.12 -m pytest`**（基线 865 passed, 2 skipped）。
- **真相源**：实施任何细节都以 `archive/2026-06-23-requirement-ledger-design.md` 为准
  （§0.1–§0.4 是 5 轮评审 changelog，§3.3.1 = F1，§3.5.1 = 终态表，§5 = impact inventory）。
- **默认交付工作目录**通常是 venture-strategy，但**本任务的工作仓是 aidazi 框架本身**（`/Users/caoruixin/projects/aidazi`）。
- 相关 memory：`scope-coverage-reporting.md`（已更新为 committed 状态）、`codex-verification-gate.md`、
  `bounded-review-runner.md`、`foldback-stance.md`、`github-push-setup.md`。

---
*生成于 2026-06-24，承接 2026-06-23 的设计 + 评审 + 提交 session。*
