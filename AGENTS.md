# AGENTS.md - Your Workspace

This is your home. Work from here.

## Session Startup

Before anything else: Read SOUL.md, USER.md, and today's memory files. Update memory after sessions.

## Red Lines

- No destructive commands without asking
- Use `trash` over `rm`
- When in doubt, ask

## Project Memory

- workspace/ = your root (`~/.qclaw/workspace/`)
- job-agent/ = AI job scanner project
- scan_strategies.py = master URL/config file

## Git 与部署

- commit message 用英文，简洁描述变更意图
- git push 仅用于跨设备同步，不要自动执行
- 部署走项目自己的命令，不依赖 git push
- **commit 前必查 jobs.json**：触发 GitHub commit 时，必须先检查 `~/.qclaw/jobs.json` 是否有改动。若有改动，应同时将 jobs.json 及其备份文件一起提交，commit message 注明 `+jobs.json update`
