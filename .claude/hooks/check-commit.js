#!/usr/bin/env node
/*
 * Claude Code 的提交门卫（PreToolUse hook，盯住 Bash 工具）。
 *
 * 作用：每当 Claude 要跑一条 Bash 命令，先经过这里。
 *   - 如果命令里包含 git commit，就检查 .claude/checks/ 下有没有两张通行证：
 *       test.pass    （单元测试全过，由 tester 生成）
 *       quality.pass （无高危安全问题，由 quality-engineer 生成）
 *     缺任意一张 → 用退出码 2 拦下这次提交，并把原因告诉 Claude。
 *   - 不是 git commit 的命令 → 直接放行。
 *
 * 与记账APP版完全一致，适用于任何项目。
 */

const fs = require('fs')
const path = require('path')

let raw = ''
process.stdin.on('data', (chunk) => { raw += chunk })
process.stdin.on('end', () => {
  let command = ''
  try {
    const input = JSON.parse(raw)
    command = (input.tool_input && input.tool_input.command) || ''
  } catch (e) {
    process.exit(0)
  }

  const isRealCommit = /(^|&&|\|\||;|\||\n)\s*git\s+commit\b/.test(command)
  if (!isRealCommit) {
    process.exit(0)
  }

  const checksDir = path.join(process.cwd(), '.claude', 'checks')
  const testPass = fs.existsSync(path.join(checksDir, 'test.pass'))
  const qualityPass = fs.existsSync(path.join(checksDir, 'quality.pass'))

  if (testPass && qualityPass) {
    process.exit(0)
  }

  const missing = []
  if (!testPass) missing.push('  - 缺少单元测试通行证（.claude/checks/test.pass）')
  if (!qualityPass) missing.push('  - 缺少质量检查通行证（.claude/checks/quality.pass）')

  process.stderr.write(
    '\n提交被门卫拦下：还没通过检查，不能提交。\n' +
    missing.join('\n') + '\n\n' +
    '请走 /gitcommit 流程——它会先跑单元测试和质量检查，两道关都过了才提交。\n'
  )
  process.exit(2)
})
