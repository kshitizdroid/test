"""li-reach — a spec-driven LinkedIn job & "we're hiring" finder.

Built on top of agent-reach's LinkedIn channel, which wires up the
`mcp-server-linkedin` MCP (https://github.com/stickerdaniel/linkedin-mcp-server)
via `mcporter`. That MCP does the authenticated scraping using *your* saved
LinkedIn login; this package sits on top of it and adds the part agent-reach
leaves to the agent: encode *your* search specifications, push them down as
native LinkedIn filters, then filter / de-duplicate / rank / report the
results.

Nothing here logs in or scrapes on its own — it shells out to the same
`mcporter call linkedin.<tool>` commands agent-reach documents.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
