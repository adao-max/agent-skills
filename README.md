# agent-skills

我自己日常在用的 AI Agent Skill 和规则，去掉个人信息后分享出来。Claude Code、Codex 等支持 Skill 的 Agent 都能用。

| Skill | 用途 |
| --- | --- |
| `chinese-writing-style` | 中文文风规则。让 Agent 写文档、报告、提示词时说人话，少一点 AI 腔。 |
| `explainer-video` | 用 Manim 画动画、配中文旁白，做 3Blue1Brown 风格的概念讲解视频（1～5 分钟，1080p MP4）。 |

## 安装

```bash
npx skills add adao-max/agent-skills                          # 交互选择要装的 Skill 和 Agent
npx skills add adao-max/agent-skills -s explainer-video -g    # 只装一个，装到用户级
```

也可以手动把 `skills/` 下对应的目录复制到 Agent 的 Skill 目录，例如 Claude Code 的 `~/.claude/skills/`、Codex 的 `~/.agents/skills/`。

## chinese-writing-style

Skill 管写文档。日常对话的回复规则在 `rules/chinese-writing.md`，要手动合并进全局规则文件：

1. 把开头「关于用户」里的占位换成你的职业和熟悉的领域。Agent 按这里判断哪些术语需要解释。
2. 把内容追加到全局规则文件，例如 Claude Code 的 `~/.claude/CLAUDE.md`、Codex 的 `~/.codex/AGENTS.md`。不要覆盖原有内容。

规则文件和 Skill 有一部分规则故意重复。日常对话只用规则文件，写文档时 Agent 再读 Skill。

## explainer-video

跟 Agent 说「做个视频讲讲 X」「用动画讲解 X」就会触发。Agent 先写提纲和旁白，生成配音和逐字时间戳，再写 Manim 场景代码、渲染，最后自动核对字幕和配音是否对齐。

依赖（macOS）：

```bash
brew install pkgconf ffmpeg
uv tool install manim
npm install -g mmx-cli
mmx auth login --api-key <你的 MiniMax API Key>
```

配音用 MiniMax TTS，需要 MiniMax 账号和余额。Linux 还要装中文字体，例如 Debian/Ubuntu 的 `fonts-noto-cjk`。视频项目默认放在 `~/video-studio/explainers/<主题>/`。
