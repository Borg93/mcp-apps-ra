<script lang="ts">
import { onMount } from "svelte";
import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";

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

function parseDocumentResult(result: CallToolResult): DocumentData | null {
  const textContent = result.content?.find((c) => c.type === "text");
  if (textContent && "text" in textContent) {
    try {
      return JSON.parse(textContent.text) as DocumentData;
    } catch {
      return null;
    }
  }
  return null;
}

let app = $state<App | null>(null);
let hostContext = $state<McpUiHostContext | undefined>();
let documentData = $state<DocumentData | null>(null);
let status = $state("");
let loading = $state(false);
let overlaysVisible = $state(true);
let tooltip = $state<{ text: string; x: number; y: number } | null>(null);
let highlightedLine = $state<string | null>(null);

// Apply host styles reactively when hostContext changes
$effect(() => {
  if (hostContext?.theme) {
    applyDocumentTheme(hostContext.theme);
  }
  if (hostContext?.styles?.variables) {
    applyHostStyleVariables(hostContext.styles.variables);
  }
  if (hostContext?.styles?.css?.fonts) {
    applyHostFonts(hostContext.styles.css.fonts);
  }
});

onMount(async () => {
  const instance = new App({ name: "Riksarkivet Viewer", version: "1.0.0" });

  instance.ontoolinput = (params) => {
    console.info("Received tool call input:", params);
  };

  instance.ontoolresult = (result) => {
    console.info("Received tool call result:", result);
    const data = parseDocumentResult(result);
    if (data && !data.error) {
      documentData = data;
    }
  };

  instance.ontoolcancelled = (params) => {
    console.info("Tool call cancelled:", params.reason);
    status = "Operation cancelled";
  };

  instance.onerror = (err) => {
    console.error("App error:", err);
    status = `Error: ${err.message}`;
  };

  instance.onhostcontextchanged = (params) => {
    hostContext = { ...hostContext, ...params };
  };

  await instance.connect();
  app = instance;
  hostContext = instance.getHostContext();
});

async function handleLineClick(line: TextLine) {
  if (!app || !documentData) return;

  loading = true;
  status = "Sending selected text...";
  try {
    await app.callServerTool({
      name: "text-line-selected",
      arguments: {
        line_id: line.id,
        transcription: line.transcription,
        document_id: documentData.imageId,
        hpos: line.hpos,
        vpos: line.vpos,
        width: line.width,
        height: line.height,
      },
    });
    status = "Text sent for translation";
  } catch (e) {
    console.error(e);
    status = "Failed to send text";
  } finally {
    loading = false;
    setTimeout(() => (status = ""), 2000);
  }
}

async function handleFetchAllText() {
  if (!app || !documentData) return;

  loading = true;
  status = "Fetching all text...";
  try {
    const transcriptions = documentData.textLines.map((line, index) => ({
      index: index + 1,
      lineId: line.id,
      text: line.transcription,
    }));

    await app.callServerTool({
      name: "fetch-all-document-text",
      arguments: {
        document_id: documentData.imageId,
        total_lines: documentData.totalLines,
        transcriptions: JSON.stringify(transcriptions),
      },
    });
    status = "All text sent for translation";
  } catch (e) {
    console.error(e);
    status = "Failed to fetch text";
  } finally {
    loading = false;
    setTimeout(() => (status = ""), 2000);
  }
}

function handleMouseEnter(line: TextLine, e: MouseEvent) {
  tooltip = { text: line.transcription, x: e.clientX + 15, y: e.clientY + 15 };
  highlightedLine = line.id;
}

function handleMouseMove(e: MouseEvent) {
  if (tooltip) {
    tooltip = { ...tooltip, x: e.clientX + 15, y: e.clientY + 15 };
  }
}

function handleMouseLeave() {
  tooltip = null;
  highlightedLine = null;
}

function toggleOverlays() {
  overlaysVisible = !overlaysVisible;
}
</script>

<main
  class="main"
  style:padding-top={hostContext?.safeAreaInsets?.top ? `${hostContext.safeAreaInsets.top}px` : undefined}
  style:padding-right={hostContext?.safeAreaInsets?.right ? `${hostContext.safeAreaInsets.right}px` : undefined}
  style:padding-bottom={hostContext?.safeAreaInsets?.bottom ? `${hostContext.safeAreaInsets.bottom}px` : undefined}
  style:padding-left={hostContext?.safeAreaInsets?.left ? `${hostContext.safeAreaInsets.left}px` : undefined}
>
  {#if !app}
    <div class="loading">Connecting...</div>
  {:else if !documentData}
    <div class="empty-state">
      <h2>Riksarkivet Document Viewer</h2>
      <p>Waiting for document data...</p>
      <p class="hint">
        Use the <code>view-document</code> tool with an image ID
        <br />
        (e.g., 'A0068523_00007')
      </p>
    </div>
  {:else if documentData.error}
    <div class="error-state">
      <h2>Error Loading Document</h2>
      <p>{documentData.message}</p>
      <p class="image-id">{documentData.imageId}</p>
    </div>
  {:else}
    <div class="viewer-wrapper">
      <div class="controls">
        <button
          class="control-btn"
          class:active={overlaysVisible}
          onclick={toggleOverlays}
        >
          {overlaysVisible ? "Hide Overlays" : "Show Overlays"}
        </button>
        <button
          class="control-btn"
          onclick={handleFetchAllText}
          disabled={loading}
        >
          Fetch All Text
        </button>
      </div>

      <div class="svg-container">
        <svg
          viewBox={`0 0 ${documentData.pageWidth} ${documentData.pageHeight}`}
          class="document-svg"
        >
          <image
            href={documentData.imageUrl}
            width={documentData.pageWidth}
            height={documentData.pageHeight}
            preserveAspectRatio="xMidYMid meet"
          />
          {#if overlaysVisible}
            <g>
              {#each documentData.textLines as line (line.id)}
                <polygon
                  points={line.polygon}
                  class="text-line-polygon"
                  class:highlighted={highlightedLine === line.id}
                  role="button"
                  tabindex="0"
                  aria-label={line.transcription}
                  onmouseenter={(e) => handleMouseEnter(line, e)}
                  onmousemove={handleMouseMove}
                  onmouseleave={handleMouseLeave}
                  onclick={() => handleLineClick(line)}
                  onkeydown={(e) => e.key === 'Enter' && handleLineClick(line)}
                />
              {/each}
            </g>
          {/if}
        </svg>
      </div>

      <div class="stats">
        <div class="stats-row">
          <span>Text lines detected:</span>
          <strong>{documentData.totalLines}</strong>
        </div>
        <div class="stats-row">
          <span>Dimensions:</span>
          <strong>{documentData.pageWidth} x {documentData.pageHeight} px</strong>
        </div>
        <div class="stats-row">
          <span>Image:</span>
          <a href={documentData.imageUrl} target="_blank" rel="noreferrer">View original</a>
        </div>
        <div class="stats-row">
          <span>ALTO XML:</span>
          <a href={documentData.altoUrl} target="_blank" rel="noreferrer">Download</a>
        </div>
      </div>

      {#if status}
        <p class="status">{status}</p>
      {/if}
    </div>
  {/if}

  {#if tooltip}
    <div class="tooltip" style:left="{tooltip.x}px" style:top="{tooltip.y}px">
      {tooltip.text}
    </div>
  {/if}
</main>

<style>
.main {
  width: 100%;
  height: 100%;
  padding: var(--spacing-sm, 0.5rem);
  display: flex;
  flex-direction: column;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  font-size: 1rem;
  color: var(--color-text-secondary);
}

.empty-state,
.error-state {
  text-align: center;
  padding: var(--spacing-lg, 2rem);
  background: var(--color-background-secondary);
  border-radius: var(--border-radius-lg, 10px);
  border: 1px solid var(--color-border-primary);
}

.empty-state h2,
.error-state h2 {
  margin: 0 0 var(--spacing-sm, 0.5rem) 0;
  font-size: var(--font-heading-lg-size, 1.25rem);
}

.error-state h2 {
  color: var(--color-error);
}

.empty-state p {
  margin: var(--spacing-sm, 0.5rem) 0;
  color: var(--color-text-secondary);
}

.empty-state code {
  background: var(--color-background-tertiary);
  padding: 0.125rem 0.5rem;
  border-radius: var(--border-radius-sm, 4px);
  font-family: var(--font-mono);
  color: var(--color-accent);
}

.image-id {
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
}

.viewer-wrapper {
  width: 100%;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md, 0.75rem);
  min-height: 0;
}

.controls {
  display: flex;
  gap: var(--spacing-sm, 0.5rem);
  align-items: center;
  flex-wrap: wrap;
}

.control-btn {
  padding: var(--spacing-sm, 0.5rem) var(--spacing-md, 1rem);
  min-width: 120px;
  background: var(--color-background-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--border-radius-md, 6px);
  color: var(--color-text-primary);
  cursor: pointer;
  font-size: var(--font-text-sm-size, 0.875rem);
  transition: all 0.2s ease;
}

.control-btn:hover {
  background: var(--color-background-tertiary);
  border-color: var(--color-accent);
}

.control-btn.active {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: var(--color-text-on-accent);
}

.control-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.hint {
  margin-left: auto;
  font-size: var(--font-text-sm-size, 0.875rem);
  color: var(--color-text-secondary);
}

.svg-container {
  width: 100%;
  flex: 1;
  background: var(--color-svg-background);
  border-radius: var(--border-radius-lg, 10px);
  border: 1px solid var(--color-border-primary);
  overflow: auto;
  min-height: 300px;
}

.document-svg {
  width: 100%;
  height: auto;
  display: block;
}

/* Claude Orange overlay polygons */
.text-line-polygon {
  fill: rgba(193, 95, 60, 0.15);
  stroke: rgba(193, 95, 60, 0.7);
  stroke-width: 2;
  cursor: pointer;
  transition: all 0.2s ease;
}

.text-line-polygon:hover {
  fill: rgba(193, 95, 60, 0.3);
  stroke: var(--claude-orange);
  stroke-width: 3;
}

.text-line-polygon.highlighted {
  fill: rgba(161, 74, 47, 0.35);
  stroke: var(--claude-orange-dark);
  stroke-width: 3;
}

.tooltip {
  position: fixed;
  background: var(--color-tooltip-background);
  color: var(--color-tooltip-text);
  padding: var(--spacing-sm, 0.5rem) var(--spacing-md, 0.75rem);
  border-radius: var(--border-radius-md, 6px);
  font-size: var(--font-text-sm-size, 0.875rem);
  pointer-events: none;
  z-index: 1000;
  max-width: 300px;
  word-wrap: break-word;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.stats {
  padding: var(--spacing-md, 0.75rem);
  background: var(--color-background-secondary);
  border-radius: var(--border-radius-lg, 10px);
  border: 1px solid var(--color-border-primary);
  font-size: var(--font-text-sm-size, 0.875rem);
}

.stats-row {
  display: flex;
  justify-content: space-between;
  margin: 0.25rem 0;
}

.stats-row span {
  color: var(--color-text-secondary);
}

.stats-row strong {
  color: var(--color-text-primary);
}

.stats-row a {
  color: var(--color-accent);
  text-decoration: none;
  transition: color 0.2s ease;
}

.stats-row a:hover {
  color: var(--color-accent-dark);
  text-decoration: underline;
}

.status {
  font-size: var(--font-text-sm-size, 0.875rem);
  color: var(--color-text-secondary);
  text-align: center;
  min-height: 1.25rem;
  margin: 0;
}
</style>
