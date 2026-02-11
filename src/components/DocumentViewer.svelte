<script lang="ts">
import type { App } from "@modelcontextprotocol/ext-apps";
import type { TextLine, DocumentData, TooltipState } from "../lib/types";

// Props
interface Props {
  app: App;
  documentData: DocumentData;
  displayMode?: "inline" | "fullscreen";
  onReset: () => void;
}

let { app, documentData, displayMode = "inline", onReset }: Props = $props();

// State
let overlaysVisible = $state(true);
let tooltip = $state<TooltipState | null>(null);
let highlightedLine = $state<string | null>(null);
let loading = $state(false);
let status = $state("");

// Handlers
async function handleLineClick(line: TextLine) {
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

<div class="viewer-wrapper" class:fullscreen={displayMode === "fullscreen"}>
  <!-- Controls -->
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
      onclick={onReset}
    >
      Upload New
    </button>
  </div>

  <!-- SVG Document Viewer -->
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

  <!-- Status Message -->
  {#if status}
    <p class="status">{status}</p>
  {/if}
</div>

<!-- Tooltip (portal to body would be better, but keeping simple) -->
{#if tooltip}
  <div class="tooltip" style:left="{tooltip.x}px" style:top="{tooltip.y}px">
    {tooltip.text}
  </div>
{/if}

<style>
.viewer-wrapper {
  width: 100%;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md, 0.75rem);
  min-height: 60vh;
}

.viewer-wrapper.fullscreen {
  min-height: 0;
  height: 100%;
}

.controls {
  display: flex;
  gap: var(--spacing-sm, 0.5rem);
  align-items: center;
  flex-wrap: wrap;
}

/* Buttons */
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

/* SVG Container */
.svg-container {
  width: 100%;
  flex: 1;
  background: var(--color-svg-background);
  border-radius: var(--border-radius-lg, 10px);
  border: 1px solid var(--color-border-primary);
  overflow: hidden;
  min-height: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.document-svg {
  width: 100%;
  height: 100%;
  display: block;
  max-width: 100%;
  max-height: 100%;
}

/* Text Line Polygons */
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

/* Tooltip */
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

/* Status */
.status {
  font-size: var(--font-text-sm-size, 0.875rem);
  color: var(--color-text-secondary);
  text-align: center;
  min-height: 1.25rem;
  margin: 0;
}
</style>
