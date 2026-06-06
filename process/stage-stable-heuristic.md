---
doc_category: live
artifact_type: reference_contract
last_reviewed: 2026-06-06
source: v3.2 §9.8
---

# Stage-Stable Heuristic — 架构相对稳定(Δ-13)

**Tier**: T0(三轨道通用)
**加载时机**: 升档 S3 / S5 时的支持证据评估
**主导**: Tech Lead + Customer 联合判定

## 命名变更:从 "架构锁" 到 "架构相对稳定"

Δ-13 把原 v2 "架构锁(architecture-stable lock)" 重命名为 "**架构相对稳定 / 阶段稳定**(stage-stable / locally stable)"。

**关键澄清**:
- 仅 **per-stage** 属性,**不**主张全局或长期
- **不是**自动门控(框架不挡升档)
- **不是**全局锁(下一个主功能可能解锁)
- 是 Tech Lead 升档时的**支持证据**之一

## 操作性启发式(非门控)

**判据**:近 5-10 commit 中
- runtime 路径占比 ≤ ~20% **且**
- semantic 路径占比 ≥ ~60% **且**
- 持续 ≥ 3 个 sub-sprint

满足上述 → "本 stage 相对稳定"的支持证据;不满足 → 不阻止升档,但 Tech Lead 需在 sprint_objective 中说明为何仍升。

**数字来源**:csagent 经验值;首例 Type A 实例应反向验证并校准(v3.2 §13.4 carry-forward)。

## 路径分类怎么算

- **runtime 路径**: orchestration / dispatcher / phase machine / tool registry / capability gating 等 substrate code
- **semantic 路径**: prompt 文件 / persona / planner 提示 / response template 等"内容"侧

具体路径前缀按项目 layout 决定,Tech Lead 在 `docs/path-classification.md`(intermediate)填空。

## 框架不提供脚本

`git log -n 10 --stat -- <runtime-paths>` 一类 grep/git 例子作为**方法论附录**,不作为框架强制工具。判断权归 Tech Lead + human。

样例命令(项目自适配):

```bash
# 近 10 commit 中 runtime 路径 LOC 变化占比
git log -n 10 --stat -- 'server/orchestrator/**' 'server/runtime/**' \
  | grep -E '^\s+\d+\s+files? changed'

# 近 10 commit 中 semantic 路径 LOC 变化占比
git log -n 10 --stat -- 'server/prompts/**' 'server/persona/**' \
  | grep -E '^\s+\d+\s+files? changed'
```

## 动态过程免责(关键)

> 架构相对稳定是 per-stage 属性,不是永久状态。新增主功能 / 引入新主路径 / 跨越生产部署边界 → 预期暂时回到 S1/S2 重走 observability + eval。这是**设计期望**而非倒退。

例如:csagent 在 M2 引入 Skill Registry 时,从"M1 阶段稳定"暂时回到 S1.5 重做架构压测期(详 `examples/csagent-reference/timeline-54-day.md` 5/17 节点)。

## Anti-pattern

- 把启发式当门控 — Tech Lead 等数字到达才升档,反而拖延 OBS/eval 进度
- 数字达标就以为永久稳定 — 下一个 milestone 引入新主路径,启发式数字会瞬间崩盘
- 不按项目校准沿用 csagent 经验值 — 不同项目 LOC 分布差异巨大(N=5-10 仅经验,首例必反向验证)
