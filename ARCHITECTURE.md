# Riksarkivet Document Viewer - Architecture Documentation

## Overview

This is an **MCP (Model Context Protocol) application** that provides an interactive document viewer for the **Swedish National Archives (Riksarkivet)**. It specializes in visualizing historical documents with ALTO XML (Analyzed Layout and Text Object) overlays, allowing users to interact with scanned documents by clicking on text lines to trigger translations from historical Swedish to modern Swedish.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCP Host (Claude)                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ MCP Protocol (HTTP/stdio)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Backend (Python/FastMCP)                     │
│  server.py                                                      │
│  ├─ MCP Tools (view-document, text-line-selected, etc.)        │
│  ├─ ALTO XML Fetching & Parsing                                │
│  └─ UI Resource Serving (ui://riksarkivet/mcp-app.html)        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ Serves bundled HTML
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Frontend (Svelte/TypeScript)                  │
│  src/                                                           │
│  ├─ App.svelte (main UI component)                             │
│  ├─ mcp-app.ts (entry point)                                   │
│  └─ global.css (styling)                                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ IIIF API Calls
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Riksarkivet IIIF API (External)                │
│  - Image API: lbiiif.riksarkivet.se/arkis!{id}/full/max/...    │
│  - ALTO XML API: lbiiif.riksarkivet.se/download/current/alto/  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
mcp-apps-ra/
├── server.py              # Python MCP server (backend)
├── mcp-app.html           # HTML entry point
├── src/
│   ├── App.svelte         # Main UI component (469 lines)
│   ├── mcp-app.ts         # App initialization & mounting
│   ├── global.css         # Design system & CSS variables
│   └── app.d.ts           # Svelte type declarations
├── dist/
│   └── mcp-app.html       # Built single-file bundle (~432 KB)
├── package.json           # Node.js dependencies & scripts
├── pyproject.toml         # Python project configuration
├── vite.config.ts         # Vite build configuration
├── tsconfig.json          # TypeScript configuration
├── Makefile               # Development workflow automation
└── uv.lock                # Python dependency lock file
```

---

## Backend Architecture (server.py)

### Technology Stack
- **FastMCP** - Fast MCP server implementation
- **httpx** - Async HTTP client for external API calls
- **Python 3.10+**

### Data Models

```python
@dataclass
class TextLine:
    id: str
    polygon: str           # SVG polygon points
    transcription: str     # Text content
    hpos: int              # Horizontal position
    vpos: int              # Vertical position
    width: int
    height: int

@dataclass
class AltoData:
    text_lines: list[TextLine]
    page_width: int
    page_height: int
    full_text: str         # Concatenated transcriptions
```

### MCP Tools

| Tool | Description | Inputs | Purpose |
|------|-------------|--------|---------|
| `view-document` | Load and display a document | `image_id` | Primary tool - fetches ALTO XML, returns image URL and text line data |
| `text-line-selected` | Handle text line clicks | `line_id`, `transcription`, `document_id` | Triggers translation request to Claude |
| `fetch-all-document-text` | Get all document text | `document_id`, `total_lines`, `transcriptions` | Bulk text export for full translation |

### Core Functions

1. **`fetch_alto_xml(image_id: str)`**
   - Fetches ALTO XML from Riksarkivet's IIIF API
   - URL: `https://lbiiif.riksarkivet.se/download/current/alto/{doc_id}?format=xml&imageid={image_id}`
   - 30-second timeout

2. **`parse_alto_xml(xml_string: str)`**
   - Regex-based XML parsing
   - Extracts page dimensions from `<Page>` element
   - Finds all `<TextLine>` elements with polygon coordinates
   - Returns structured `AltoData` object

### Resource Serving

```python
@mcp.resource("ui://riksarkivet/mcp-app.html")
def get_mcp_app_html() -> str:
    # Serves dist/mcp-app.html as text/html;profile=mcp-app
```

### Server Modes

| Mode | Transport | Use Case |
|------|-----------|----------|
| HTTP (default) | Port 3001, streamable-http | Development & testing |
| Stdio | stdin/stdout | Claude Desktop integration |

---

## Frontend Architecture (Svelte/TypeScript)

### Technology Stack
- **Svelte 5.0** with runes (modern reactivity)
- **TypeScript 5.9**
- **MCP SDK** (`@modelcontextprotocol/ext-apps`)
- **Vite 6.0** (build system)

### Type Definitions

```typescript
interface TextLine {
    id: string;
    polygon: string;
    transcription: string;
    hpos: number;
    vpos: number;
    width: number;
    height: number;
}

interface DocumentData {
    imageId: string;
    imageUrl: string;
    altoUrl: string;
    pageWidth: number;
    pageHeight: number;
    textLines: TextLine[];
    totalLines: number;
    fullText: string;
    error?: boolean;
    message?: string;
}
```

### State Management (Svelte Runes)

```typescript
let app = $state<App | null>(null);           // MCP connection
let hostContext = $state<McpUiHostContext>(); // Theme & styles
let documentData = $state<DocumentData>();     // Loaded document
let status = $state<string>("");               // User feedback
let loading = $state<boolean>(true);           // Async flag
let overlaysVisible = $state<boolean>(true);   // Toggle overlays
let tooltip = $state<{text, x, y} | null>();   // Hover tooltip
let highlightedLine = $state<string | null>(); // Hovered line
```

### Component Lifecycle

```
onMount()
    │
    ├─ Create App instance (MCP SDK)
    │
    ├─ Register event handlers:
    │   ├─ ontoolinput    → Tool call initiated
    │   ├─ ontoolresult   → Parse JSON, update documentData
    │   ├─ ontoolcancelled → Handle cancellation
    │   ├─ onerror        → Error handling
    │   └─ onhostcontextchanged → Theme updates
    │
    ├─ Connect to MCP host
    │
    └─ Set loading = false

$effect()
    │
    └─ Apply host styles (theme, CSS variables, fonts)
```

### Event Handlers

| Handler | Trigger | Action |
|---------|---------|--------|
| `handleLineClick(line)` | Click on text line | Calls `text-line-selected` tool |
| `handleFetchAllText()` | "Fetch All Text" button | Calls `fetch-all-document-text` tool |
| `handleMouseEnter(line, event)` | Hover on line | Shows tooltip |
| `handleMouseMove(event)` | Mouse move | Updates tooltip position |
| `handleMouseLeave()` | Mouse leave | Hides tooltip |

### Rendering States

1. **Loading**: "Connecting..." spinner
2. **Empty**: Waiting for document (shows usage hint)
3. **Error**: Error message with image ID
4. **Loaded**: Interactive document viewer with SVG overlays

### UI Components

```
┌─────────────────────────────────────────────────────────────┐
│  Controls: [Toggle Overlays] [Fetch All Text]               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │              SVG Document Viewer                    │   │
│  │  ┌─────────────────────────────────────────────┐   │   │
│  │  │  Background: IIIF Image                     │   │   │
│  │  │  Overlays: Clickable Polygon Text Lines     │   │   │
│  │  └─────────────────────────────────────────────┘   │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Stats: Lines: X | Dimensions: WxH | [Links]               │
├─────────────────────────────────────────────────────────────┤
│  Status Messages (transient, 2-second timeout)             │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
    ┌─────────────┐
    │  Tooltip    │  (floating, follows mouse)
    │  "Text..."  │
    └─────────────┘
```

---

## Communication Flow

### Frontend → Backend

```
User clicks text line
        │
        ▼
App.svelte: handleLineClick(line)
        │
        ▼
app.callServerTool("text-line-selected", {
    line_id: "...",
    transcription: "...",
    document_id: "..."
})
        │
        ▼
MCP Protocol (HTTP/stdio)
        │
        ▼
server.py: @mcp.tool() text_line_selected()
        │
        ▼
Returns translation prompt to Claude
```

### Backend → Frontend

```
Python tool returns JSON string
        │
        ▼
MCP wraps in CallToolResult
        │
        ▼
Frontend: instance.ontoolresult callback
        │
        ▼
parseDocumentResult() extracts & parses JSON
        │
        ▼
documentData = $state(...) updated
        │
        ▼
Svelte reactivity triggers re-render
```

---

## Build System

### Vite Configuration

```typescript
// vite.config.ts
export default defineConfig({
    plugins: [
        svelte({ preprocess: vitePreprocess(), runes: true }),
        viteSingleFile()  // Bundles everything into one HTML
    ],
    build: {
        rollupOptions: {
            input: process.env.INPUT  // Controlled by env var
        }
    }
});
```

### Build Scripts

```bash
# Development (watch mode with sourcemaps)
npm run dev

# Production build
npm run build    # tsc --noEmit && vite build

# Build output: dist/mcp-app.html (single file, ~432 KB)
```

### Makefile Targets

| Target | Command | Purpose |
|--------|---------|---------|
| `make install` | npm install + uv sync | Install all dependencies |
| `make build` | npm run build | Build frontend |
| `make dev` | npm run dev | Watch mode development |
| `make serve` | build + python server.py | Run HTTP server |
| `make serve-stdio` | build + python server.py --stdio | Run for Claude Desktop |
| `make inspect` | npx @mcpjam/inspector | MCP debugging |
| `make clean` | rm -rf dist node_modules .venv | Clean artifacts |

---

## External API Integration

### Riksarkivet IIIF API

| Endpoint | URL Pattern | Purpose |
|----------|-------------|---------|
| Image | `https://lbiiif.riksarkivet.se/arkis!{image_id}/full/max/0/default.jpg` | Full resolution document image |
| ALTO XML | `https://lbiiif.riksarkivet.se/download/current/alto/{doc_id}?format=xml&imageid={image_id}` | Text coordinates & transcriptions |

**Image ID Format**: `A0068523_00007` where:
- `A0068523` = Document ID
- `00007` = Page number

---

## Key Design Patterns

### Backend

| Pattern | Implementation |
|---------|----------------|
| Dataclass Models | Type-safe data structures (TextLine, AltoData) |
| Regex-based Parsing | XML parsing via regex (performant) |
| Error Handling | Try/catch with JSON error responses |
| Resource URI | `ui://` protocol for serving embedded UI |

### Frontend

| Pattern | Implementation |
|---------|----------------|
| Svelte Runes | Modern reactivity with `$state`, `$effect` |
| Host Integration | Respects host theme via callback API |
| SVG Visualization | Interactive vector graphics for overlays |
| Accessibility | ARIA labels, keyboard navigation |

### Build

| Pattern | Implementation |
|---------|----------------|
| Single-file Distribution | viteSingleFile bundles all assets |
| Environment Configuration | INPUT env var controls build input |
| Type Safety | TypeScript strict mode throughout |

---

## File Responsibilities

| File | Responsibility |
|------|----------------|
| `server.py` | MCP server, ALTO parsing, tool definitions, resource serving |
| `App.svelte` | Main UI component, document viewer, event handling, state |
| `mcp-app.ts` | App initialization, Svelte component mounting |
| `global.css` | Design system, CSS variables, typography |
| `app.d.ts` | Svelte type declarations |
| `mcp-app.html` | HTML entry point with mount target |
| `vite.config.ts` | Build configuration, plugins |
| `tsconfig.json` | TypeScript strict mode, ESNext target |
| `package.json` | Node.js dependencies, build scripts |
| `pyproject.toml` | Python dependencies, entry point |
| `Makefile` | Development workflow automation |

---

## Development Workflow

```bash
# 1. Install dependencies
make install

# 2. Start development (watch mode)
make dev           # In terminal 1

# 3. Run server
make serve         # In terminal 2 (HTTP mode)
# OR
make serve-stdio   # For Claude Desktop

# 4. Debug with MCP Inspector
make inspect

# 5. Build for production
make build

# 6. Clean up
make clean
```

---

## Key Features

1. **Document Loading** - Fetch and parse ALTO XML with coordinates
2. **Interactive Overlays** - Clickable polygon overlays on text regions
3. **Hover Tooltips** - Show transcriptions on hover
4. **Toggle Overlays** - Show/hide all polygons
5. **Bulk Text Export** - Fetch all text for batch translation
6. **Responsive Design** - Adapts to screen sizes
7. **Theme Integration** - Respects host application theme
8. **Accessibility** - ARIA labels, keyboard support (Enter key)
9. **Error Handling** - Graceful degradation with user messages
10. **Single-file Distribution** - One HTML file for easy deployment
