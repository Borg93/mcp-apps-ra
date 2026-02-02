# Riksarkivet Document Viewer

Interactive document viewer for Swedish National Archives with ALTO XML visualization.

## Quick Start

```bash
make install
make serve
```

## Tools

| Tool | Description |
|------|-------------|
| `view-document` | Load document with interactive ALTO overlay |
| `text-line-selected` | Translate selected text line |
| `fetch-all-document-text` | Get all document text for translation |

## Project Structure

```
├── server.py           # Python FastMCP server
├── pyproject.toml      # Python dependencies
├── src/
│   ├── App.svelte      # Svelte UI component
│   ├── mcp-app.ts      # Entry point
│   └── global.css      # Global styles
├── mcp-app.html        # HTML entry
├── dist/               # Built output
├── vite.config.ts      # Vite + Svelte config
├── svelte.config.js
└── package.json
```

## Make Commands

| Command | Description |
|---------|-------------|
| `make install` | Install dependencies |
| `make build` | Build frontend |
| `make serve` | Run HTTP server (port 3001) |
| `make serve-stdio` | Run stdio server |

## Usage

Call `view-document` with an image ID (e.g., `A0068523_00007`) to load a document from Riksarkivet.
# mcp-apps-ra
