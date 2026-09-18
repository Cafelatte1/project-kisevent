# KIS Event

A local, single-user service that collects Korea Investment & Securities (한국투자증권) event notices into SQLite and lets an AI agent answer "which events are open to branch customers right now?" over MCP. Event content lives inside banner images, so the agent reads the image, summarizes the target customers and criteria, and then answers.

- Install and connect: `SETUP.md` (Korean; tell the agent "셋팅해줘" and it follows the document)
- Dashboard (status board): http://127.0.0.1:4000
- MCP: HTTP `http://127.0.0.1:4000/mcp` (Claude Code picks it up from `.mcp.json`); Claude Desktop uses stdio
- Agent guidance: `CLAUDE.md` for Claude, `AGENTS.md` for Codex. Design rationale: `docs/event-page-research.md` (Korean)

## Agent model requirements

There are two roles.
- **Main session** — takes the user's question and drives the flow `sync_now → query → (dispatch analysis if anything is unsummarized) → answer`.
- **Subagent `event-analyzer`** — reads a banner and saves the target/criteria JSON. In Claude Code it is `.claude/agents/event-analyzer.md`; in Codex it is `~/.codex/agents/event-analyzer.toml` (copied from this repo's `.codex/agents/`). Each instance handles two unsummarized images and the instances run in parallel. Where no subagents exist (Claude Desktop) the main session does the same work itself.

| | Subagent (`event-analyzer`) | Main session |
|---|---|---|
| **Claude** minimum / recommended | Sonnet low / Sonnet medium | Sonnet medium / Sonnet high |
| **GPT** (`gpt-5.6-luna`) minimum / recommended | Luna medium / Luna high | Luna high / Luna xhigh |

Defaults are Sonnet medium (`effort: medium`) for the Claude subagent and Luna high for the Codex one. In a check over 33 ongoing and 20 ended banners the info block was found in 53/53 and no target was misjudged (`docs/event-page-research.md` §8).
