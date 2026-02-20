<script lang="ts">
import { onMount, onDestroy } from "svelte";
import type { App } from "@modelcontextprotocol/ext-apps";
import type { TextLine, PageData, PageAltoData, TooltipState } from "../lib/types";
import type { PolygonHit } from "../lib/geometry";
import { buildPolygonHits, findHitAtImageCoord } from "../lib/geometry";
import { CanvasController, type Transform } from "../lib/canvas";
import TranscriptionPanel from "./TranscriptionPanel.svelte";
import CanvasToolbar from "./CanvasToolbar.svelte";

interface Props {
  app: App;
  pageData: PageData;
  pageIndex: number;
  totalPages: number;
  pageMetadata: string;
  onPageChange: (index: number) => void;
  canFullscreen: boolean;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
}

let { app, pageData, pageIndex, totalPages, pageMetadata, onPageChange, canFullscreen, isFullscreen, onToggleFullscreen }: Props = $props();

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let tooltip = $state<TooltipState | null>(null);
let highlightedLineId = $state<string | null>(null);
let showPanel = $state(false);
let panelWidth = $state(280);

let textLines = $derived(pageData?.alto?.textLines ?? []);
let hasTextLines = $derived(textLines.length > 0);

// Canvas element refs
let canvasEl: HTMLCanvasElement;
let containerEl: HTMLDivElement;
let wrapperEl: HTMLDivElement;

// Current page ALTO data
let currentAlto: PageAltoData | null = null;

// Parsed polygon data for hit testing (image coordinates)
let currentPolygons: PolygonHit[] = [];

let controller: CanvasController;

// ---------------------------------------------------------------------------
// CanvasController callbacks
// ---------------------------------------------------------------------------

/** Draw polygon overlays in image space (called by CanvasController after drawing the image) */
function drawOverlays(ctx: CanvasRenderingContext2D, transform: Transform) {
  if (currentPolygons.length === 0) return;

  for (const p of currentPolygons) {
    const isHighlighted = p.lineId === highlightedLineId;
    ctx.beginPath();
    ctx.moveTo(p.points[0], p.points[1]);
    for (let i = 2; i < p.points.length; i += 2) {
      ctx.lineTo(p.points[i], p.points[i + 1]);
    }
    ctx.closePath();

    ctx.fillStyle = isHighlighted ? "rgba(193, 95, 60, 0.3)" : "rgba(193, 95, 60, 0.15)";
    ctx.fill();
    ctx.strokeStyle = isHighlighted ? "rgba(193, 95, 60, 1)" : "rgba(193, 95, 60, 0.7)";
    ctx.lineWidth = isHighlighted ? 3 / transform.scale : 2 / transform.scale;
    ctx.stroke();
  }
}

/** Handle hover — hit test polygons, set tooltip + highlight, return cursor */
function handleHover(imgX: number, imgY: number, screenX: number, screenY: number): string | null {
  if (!currentPolygons.length) {
    if (tooltip) { tooltip = null; highlightedLineId = null; controller.requestDraw(); }
    return null;
  }

  // When the transcription panel is open, skip tooltip (avoids double info)
  if (showPanel) {
    if (tooltip) { tooltip = null; }
    return null;
  }

  const hit = findHitAtImageCoord(imgX, imgY, currentPolygons);
  if (hit) {
    tooltip = { text: hit.line.transcription, x: screenX + 15, y: screenY + 15 };
    if (highlightedLineId !== hit.lineId) {
      highlightedLineId = hit.lineId;
      controller.requestDraw();
    }
    return "pointer";
  }

  if (tooltip) {
    tooltip = null;
    highlightedLineId = null;
    controller.requestDraw();
  }
  return null;
}

/** Handle click — hit test polygons, update model context */
function handleClick(imgX: number, imgY: number) {
  if (!currentPolygons.length) return;
  const hit = findHitAtImageCoord(imgX, imgY, currentPolygons);
  if (hit) scheduleContextUpdate(hit.line);
}

/** Handle pointer leave — clear tooltip + highlight */
function handlePointerLeave() {
  tooltip = null;
  if (highlightedLineId) {
    highlightedLineId = null;
    controller.requestDraw();
  }
}

// ---------------------------------------------------------------------------
// Transcription panel handlers
// ---------------------------------------------------------------------------

function handlePanelLineHover(lineId: string | null) {
  if (lineId === highlightedLineId) return;
  highlightedLineId = lineId;
  tooltip = null;
  controller?.requestDraw();
}

function handlePanelLineClick(line: TextLine) {
  const centerX = line.hpos + line.width / 2;
  const centerY = line.vpos + line.height / 2;
  if (!controller?.isPointVisible(centerX, centerY)) {
    controller?.centerOn(centerX, centerY);
  }
  scheduleContextUpdate(line);
}

// ---------------------------------------------------------------------------
// Model context + text selection (debounced, capability-checked)
// ---------------------------------------------------------------------------

let contextTimer: ReturnType<typeof setTimeout> | null = null;
let lastSentContext = "";

function scheduleContextUpdate(selectedLine?: TextLine) {
  if (contextTimer) clearTimeout(contextTimer);
  // Immediate for text selection (user clicked), debounced for page changes
  const delay = selectedLine ? 0 : 500;
  contextTimer = setTimeout(() => sendContextUpdate(selectedLine), delay);
}

async function sendContextUpdate(selectedLine?: TextLine) {
  if (!app) return;
  const caps = app.getHostCapabilities();
  if (!caps?.updateModelContext) return;

  const page = pageIndex + 1;
  const lines = currentAlto?.textLines ?? [];
  const fullText = lines.map(l => l.transcription).join("\n");

  const parts = [`Document viewer: page ${page}/${totalPages}`];
  if (pageMetadata) parts.push(`Page metadata: ${pageMetadata}`);
  if (selectedLine) parts.push(`User selected text: "${selectedLine.transcription}"`);
  parts.push(fullText ? `Full page transcription:\n${fullText}` : "(no transcribed text on this page)");

  const text = parts.join("\n");
  if (text === lastSentContext) return;
  lastSentContext = text;

  try {
    await app.updateModelContext({
      content: [{ type: "text", text }],
    });
  } catch (e) {
    console.error("[updateModelContext]", e);
  }
}

// ---------------------------------------------------------------------------
// Watch pageData changes — load image and set on controller
// ---------------------------------------------------------------------------

$effect(() => {
  const pd = pageData;

  currentAlto = pd.alto;
  currentPolygons = currentAlto?.textLines ? buildPolygonHits(currentAlto.textLines) : [];
  highlightedLineId = null;
  tooltip = null;

  const img = new Image();
  let cancelled = false;

  img.onload = () => {
    if (cancelled) return;
    if (controller) {
      controller.setImage(img);
      scheduleContextUpdate();
    }
  };
  img.onerror = () => {
    if (cancelled) return;
    console.error("Failed to load page image");
  };
  img.src = pd.imageDataUrl;

  return () => {
    cancelled = true;
    img.onload = null;
    img.onerror = null;
    img.src = "";  // Abort any in-progress load
  };
});

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

// Canvas event wrappers — delegate to controller (created in onMount)
function onPointerDown(e: PointerEvent) { controller?.handlePointerDown(e); }
function onPointerMove(e: PointerEvent) { controller?.handlePointerMove(e); }
function onPointerUp(e: PointerEvent) { controller?.handlePointerUp(e); }
function onPointerLeave() { controller?.handlePointerLeave(); }
function onWheel(e: WheelEvent) { controller?.handleWheel(e); }

onMount(() => {
  controller = new CanvasController(canvasEl, containerEl, wrapperEl, {
    onAfterDraw: drawOverlays,
    onClickImage: handleClick,
    onHoverImage: handleHover,
    onPointerLeave: handlePointerLeave,
  });
});

onDestroy(() => {
  controller?.destroy();
});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="viewer-wrapper" bind:this={wrapperEl}>
  <!-- Canvas -->
  <div class="canvas-container" bind:this={containerEl}>
    <canvas
      bind:this={canvasEl}
      style="cursor: grab"
      onpointerdown={onPointerDown}
      onpointermove={onPointerMove}
      onpointerup={onPointerUp}
      onpointerleave={onPointerLeave}
      onwheel={onWheel}
    ></canvas>
    {#if pageMetadata}
      <div class="page-info">{pageMetadata}</div>
    {/if}

    <CanvasToolbar
      showTranscription={showPanel}
      hasTranscription={hasTextLines}
      {canFullscreen}
      {isFullscreen}
      rightOffset={showPanel ? panelWidth : 0}
      onToggleTranscription={() => showPanel = !showPanel}
      onResetView={() => controller?.resetView()}
      {onToggleFullscreen}
    />

    {#if hasTextLines}
      <TranscriptionPanel
        {textLines}
        {highlightedLineId}
        open={showPanel}
        width={panelWidth}
        onWidthChange={(w) => panelWidth = w}
        onLineHover={handlePanelLineHover}
        onLineClick={handlePanelLineClick}
      />
    {/if}
  </div>
</div>

<!-- Tooltip -->
{#if tooltip && tooltip.x > 0}
  <div class="tooltip" style:left="{tooltip.x}px" style:top="{tooltip.y}px">
    {tooltip.text}
  </div>
{/if}

<style>
.viewer-wrapper {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.canvas-container {
  flex: 1;
  background: var(--color-background-secondary, light-dark(#f5f4ed, #201d18));
  overflow: hidden;
  position: relative;
}
.canvas-container canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.page-info {
  position: absolute;
  top: 8px;
  left: 8px;
  background: rgba(0, 0, 0, 0.2);
  color: rgba(255, 255, 255, 0.6);
  padding: 2px 8px;
  border-radius: var(--border-radius-sm, 4px);
  font-size: var(--font-text-xs-size, 0.75rem);
  white-space: nowrap;
  pointer-events: none;
  z-index: 10;
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tooltip {
  position: fixed;
  background: var(--color-tooltip-background, light-dark(rgba(44, 44, 44, 0.95), rgba(232, 230, 227, 0.95)));
  color: var(--color-tooltip-text, light-dark(#faf9f5, #1a1815));
  padding: var(--spacing-sm, 0.5rem) var(--spacing-md, 0.75rem);
  border-radius: var(--border-radius-md, 6px);
  font-size: var(--font-text-sm-size, 0.875rem);
  pointer-events: none;
  z-index: 1000;
  max-width: 300px;
  word-wrap: break-word;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
</style>
