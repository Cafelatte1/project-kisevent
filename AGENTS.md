# AGENTS.md — guidance for Codex (GPT)

Codex CLI and the ChatGPT Codex app read this file. `CLAUDE.md` is the equivalent for Claude Code and is the source of truth for the project description, directory layout, commands and FronyBoard rules — read it first before any development work.

## When the user says "셋팅해줘" (set it up)
Follow `SETUP.md` from top to bottom. For the Codex connection use its "Codex(GPT) 연결" section.

## Answering event questions (kis-event MCP)
Event content lives inside banner images, so the relevant banners must be summarized before you answer.
1. Before the first event query of a conversation call `sync_now` once (it waits for the collection to finish). Do not call it again in the same conversation.
2. Pick events with `list_events(target)` or `events_on(date, target)`. `pending_summaries > 0` means some banners are unsummarized.
3. Take the unsummarized image_ids from `batches` in the `sync_now` response (ongoing events) or from `list_pending_summaries(event_nums=…)`. They are already split into groups of two.
4. **Spawn one custom agent `event-analyzer` per batch, all at the same time** (e.g. 5 ids → `[[a,b],[c,d],[e]]` → 3 agents). The agent must exist at `~/.codex/agents/event-analyzer.toml`; if it does not, copy this repo's `.codex/agents/event-analyzer.toml` there. The main session must not call `get_summary_tiles` itself and work through images one by one; only if the agent truly cannot be spawned, run `get_summary_tiles(image_id)` → `save_summary(image_id, summary)` per image directly.
5. Query again and answer. Unsummarized events have `target_types` null, so they stay in the result even with a target filter.

Backfilling past events is done only from the dashboard button (`http://127.0.0.1:4000`); there is no MCP tool for it.

## Summary JSON (schema_version 2)
The guide in the `get_summary_tiles` response is the source of truth. Order: `analysis` (what the image shows) → `block_found` → `target {types, text, conditions, exclusions}` → `criteria {text, products, performance} | null`. When `block_found` is false, omit target and criteria. If `save_summary` returns `ok: false`, fix the JSON as `errors` says and save again.
