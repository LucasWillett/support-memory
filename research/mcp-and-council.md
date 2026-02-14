# Research: MCP & LM-Council

*Researched by Browser Claude, 2026-02-13*

## Model Context Protocol (MCP)

**What it is:** An open-source standard that works like a USB-C port for AI, enabling LLMs to connect to external systems, data sources, and tools in a standardized way.

**Key features:**
- Standardized connectivity between AI and external tools
- Protocol for tool discovery and invocation
- Used by Claude Code, Mira (CEO's system), and others

**Relevance to support-memory:**
- Could replace custom integrations (Slack, Zendesk, ChurnZero) with standardized MCP servers
- Would allow any MCP-compatible AI to access our shared memory
- Future-proofs the architecture

**Resources:**
- https://modelcontextprotocol.io
- https://github.com/modelcontextprotocol/servers

---

## Language Model Council (lm-council)

**What it is:** A democratic framework where multiple LLMs evaluate each other by consensus rather than relying on single evaluators. Published at NAACL 2025.

**How it works:**
- Multiple models weigh in on a question
- Consensus is reached democratically
- Reduces single-model bias

**Relevance to support-memory:**
- Aligns with our "voices" concept (Support, GTM, CSM, etc.)
- Could use multiple LLMs instead of/in addition to multiple personas
- Provides academic foundation for multi-agent decision making

**Resources:**
- https://github.com/jascha/llm-council (CEO's implementation)
- NAACL 2025 paper

---

## Recommendations for Support-Memory

1. **Near-term:** Continue with current architecture (voices + shared memory)
2. **Medium-term:** Consider wrapping shared_memory.py as an MCP server
3. **Long-term:** Integrate lm-council for high-stakes decisions (escalations, launches)

The combination creates: **standardized connectivity (MCP) + democratic consensus (lm-council) + domain expertise (voices) + shared context (memory)**
