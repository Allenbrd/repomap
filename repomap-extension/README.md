# RepoMap Extension

Live view of RepoMap MCP tool calls in Cursor's sidebar — blast radius analysis, dependency paths, risk scores, and policy violations rendered in real time.

## Install

```bash
cd repomap-extension
npm install
npm run package
```

Then in Cursor: Extensions sidebar → `...` menu → "Install from VSIX..." → select the generated `.vsix` file.

## How it works

The extension inserts a transparent proxy between Cursor and the repomap MCP server. The proxy forwards all MCP traffic byte-for-byte while logging tool calls to `~/.repomap/events.jsonl`. The extension tail-follows that log and renders events in the sidebar.

On first activation the extension automatically wraps the `repomap` entry in `.cursor/mcp.json` with the proxy. No manual config changes needed.
