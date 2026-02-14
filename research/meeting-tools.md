# Meeting Tools Integration Research

*Researched by Scout, 2026-02-13*

## Granola

**API:** https://docs.granola.ai (Enterprise API)

- **Auth:** API Key (Settings → Workspaces → API tab)
- **Rate limits:** 25 req/5sec burst, 5 req/sec sustained
- **Features:** RESTful API for meeting notes and workspace data
- **MCP Server:** None exists yet

**Note:** May require enterprise plan for API access.

---

## Fathom

**API:** https://developers.fathom.ai

- **Auth:** API Key or OAuth
- **SDKs:** TypeScript and Python available
- **Features:**
  - Webhooks for meeting events
  - Transcript export
  - Recording access
- **MCP Server:** None exists yet

**Note:** More accessible than Granola (no enterprise requirement), better export options.

---

## Recommendation

**Start with Fathom** - better documented, more accessible, has SDKs.

**Integration approach:**
1. Get Fathom API key
2. Build `sync_from_fathom.py` (same pattern as Slack listener)
3. Pull recent meeting transcripts → extract key points → write to memory.json
4. Later: Build MCP server for broader compatibility

---

## Next Steps

- [ ] Get Fathom API key from settings
- [ ] Test API access to recent meetings
- [ ] Build sync script
- [ ] Add Granola later if enterprise access available
