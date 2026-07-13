---
name: gitcommit
description: 安全存档。先并行跑单元测试(tester)和质量检查(quality-engineer)两道关，两道都通过了才调用 /git-save 提交并推送，push 成功后清理通行证。当用户说"安全提交""检查后再存档""gitcommit""跑完检查再提交"时使用。
---

# gitcommit — 检查通过才允许存档

这是"带门禁的存档"。核心规矩:**先过检查,再存档。** 单元测试和质量检查两道关都通过,才允许调用 `/git-save` 提交并推送。

> 为什么要有它:项目里装了一个提交门卫(配在 `.claude/settings.json` 的 PreToolUse hook,脚本是 `.claude/hooks/check-commit.js`)。每当 Claude 要跑 `git commit`,门卫先检查 `.claude/checks/` 下有没有两张通行证(`test.pass` 和 `quality.pass`)。没有就直接拒绝提交。这两张通行证只能由 tester 和 quality-engineer 干完活、确认通过后生成。本技能负责把这套流程串起来。

## 面对的用户

用户是编程小白,看不懂技术黑话。每一步都用大白话简单说明在做什么、结果如何。

## 操作步骤

### 第一步:清掉旧通行证,从干净状态开始

先删掉上一次可能残留的通行证,避免拿旧结果蒙混:

```
rm -f .claude/checks/test.pass .claude/checks/quality.pass
```

告诉用户:"开始检查前先清场,确保这次用的是全新的检查结果。"

### 第二步:并行跑两道检查关

**同时**派出两个 subagent(在同一条回复里一起发起,让它们并行干活,省时间):

1. **tester** —— 跑单元测试。全过就写 `.claude/checks/test.pass`,有失败就不写。
2. **quality-engineer** —— 做质量检查。无高危安全问题就写 `.claude/checks/quality.pass`,有高危就不写。

等两个都干完,收集它们的报告。

### 第三步:验通行证,决定放不放行

检查 `.claude/checks/` 下两张通行证在不在:

```
ls .claude/checks/test.pass .claude/checks/quality.pass
```

- **两张都在** → 检查通过,进入第四步存档。
- **缺任意一张** → **中止,不提交**。用大白话告诉用户:哪一关没过、具体什么问题(测试挂了哪几项 / 有什么高危安全问题)、怎么改。修好后再重新跑 `/gitcommit`。

不许在检查没全过时硬造通行证或跳过这一步。

### 第四步:调 /git-save 存档并推送

两关都过了,调用 `/git-save` 技能完成提交和推送。`/git-save` 是独立技能,保持它原本的业务逻辑不变(看改动 → 提交 → 推送 GitHub → 确认结果)。

> 提醒:推送到 GitHub 属于"对外发布",按 `/git-save` 的规矩,推送前要让用户明确知道。

### 第五步:push 成功后清理通行证

确认 `/git-save` **推送成功**后,删掉两张通行证:

```
rm -f .claude/checks/test.pass .claude/checks/quality.pass
```

这样下次存档必须重新跑一遍检查,杜绝旧通行证被复用。

- 若 push 失败(网络/认证/冲突):**先别删通行证**,留着,等用户把 push 的问题解决后可以直接再推,不用白跑一遍检查。把失败原因如实告诉用户。

## 铁律

- 顺序不能反:**先检查、后存档**。检查没全过绝不提交。
- 通行证只反映真实检查结果,绝不凭空生成。
- 只有 push 真正成功了才清理通行证;push 没成功就保留。
- `/git-save` 保持独立,本技能只负责"检查 + 编排",不改 `/git-save` 的逻辑。
