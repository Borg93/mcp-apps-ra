<script lang="ts">
import { onMount, onDestroy } from "svelte";
import OpenSeadragon from "openseadragon";
import Konva from "konva";

import type { App } from "@modelcontextprotocol/ext-apps";
import type { TextLine, TooltipState, ViewerData, PageAltoData, ImageChunk } from "../lib/types";

interface Props {
  app: App;
  data: ViewerData;
  displayMode?: "inline" | "fullscreen";
}

let { app, data, displayMode = "inline" }: Props = $props();

const CHUNK_SIZE = 512 * 1024;

// State
let overlaysVisible = $state(true);
let currentPageIndex = $state(0);
let tooltip = $state<TooltipState | null>(null);
let highlightedLineId = $state<string | null>(null);
let status = $state("");
let pageStatus = $state("");
let osdContainer: HTMLDivElement;

// Derived
let totalPages = $derived(data.imageUrls.length);

// Current page data (loaded on demand via callServerTool)
let currentAlto = $state<PageAltoData | null>(null);

// OSD + Konva instances
let viewer: OpenSeadragon.Viewer | null = null;
let stage: Konva.Stage | null = null;
let layer: Konva.Layer | null = null;
let konvaDiv: HTMLDivElement | null = null;

// Shape lookup for highlight updates
let shapeMap = new Map<string, Konva.Line>();

// Parsed polygon data for hit testing (image coordinates)
let currentPolygons: { lineId: string; points: number[]; line: TextLine }[] = [];

// Drag detection
let mouseDownPos: { x: number; y: number } | null = null;

// rAF-throttled sync flag
let syncRequested = false;

// Cleanup handles
let resizeObserver: ResizeObserver | null = null;
let blobUrls: string[] = [];

// ---------------------------------------------------------------------------
// Data Loading — server fetches everything, app receives data
// ---------------------------------------------------------------------------

/**
 * Load image bytes from the server in chunks (like PDF server's read_pdf_bytes).
 * Returns a local blob URL that OSD can render directly.
 */
async function loadImageBytes(imageUrl: string): Promise<string> {
  const chunks: Uint8Array[] = [];
  let offset = 0;
  let hasMore = true;
  let totalBytes = 0;

  pageStatus = "Loading image...";

  while (hasMore) {
    const result = await app.callServerTool({
      name: "read-image-bytes",
      arguments: { url: imageUrl, offset, byte_count: CHUNK_SIZE },
    });

    if (result.isError) {
      const msg = result.content?.map((c: any) => ("text" in c ? c.text : "")).join(" ");
      throw new Error(msg || "Failed to load image");
    }

    const sc = (result as any).structuredContent as ImageChunk | undefined;
    if (!sc) throw new Error("No structuredContent in image response");

    totalBytes = sc.totalBytes;
    hasMore = sc.hasMore;

    // Decode base64 chunk
    const binaryString = atob(sc.bytes);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    chunks.push(bytes);

    offset += sc.byteCount;
    const pct = Math.round((offset / totalBytes) * 100);
    pageStatus = `Loading image... ${pct}%`;
  }

  // Assemble chunks into a blob URL
  const fullData = new Uint8Array(totalBytes);
  let pos = 0;
  for (const chunk of chunks) {
    fullData.set(chunk, pos);
    pos += chunk.length;
  }

  const blob = new Blob([fullData], { type: "image/jpeg" });
  const blobUrl = URL.createObjectURL(blob);
  blobUrls.push(blobUrl);
  console.log(`[Image] Loaded ${totalBytes} bytes in ${chunks.length} chunk(s)`);
  return blobUrl;
}

/**
 * Load and parse ALTO XML via the server (like PDF server's chunked loading).
 * Server fetches the XML, parses it, returns structured text line data.
 */
async function loadAlto(altoUrl: string): Promise<PageAltoData> {
  pageStatus = "Loading text overlay...";

  const result = await app.callServerTool({
    name: "read-alto",
    arguments: { url: altoUrl },
  });

  if (result.isError) {
    const msg = result.content?.map((c: any) => ("text" in c ? c.text : "")).join(" ");
    throw new Error(msg || "Failed to load ALTO");
  }

  const sc = (result as any).structuredContent as PageAltoData | undefined;
  if (!sc) throw new Error("No structuredContent in ALTO response");

  console.log(`[ALTO] ${sc.textLines.length} text lines, ${sc.pageWidth}x${sc.pageHeight}`);
  return sc;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Parse ALTO polygon "x1,y1 x2,y2 ..." → flat [x1,y1,x2,y2,...] */
function parsePolygonPoints(polygon: string): number[] {
  const pts: number[] = [];
  for (const pair of polygon.trim().split(/\s+/)) {
    const [x, y] = pair.split(",").map(Number);
    if (!isNaN(x) && !isNaN(y)) pts.push(x, y);
  }
  return pts;
}

/** Ray-casting point-in-polygon */
function pointInPolygon(px: number, py: number, pts: number[]): boolean {
  let inside = false;
  for (let i = 0, j = pts.length - 2; i < pts.length; j = i, i += 2) {
    const xi = pts[i], yi = pts[i + 1];
    const xj = pts[j], yj = pts[j + 1];
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

function findLineAtImageCoord(imgX: number, imgY: number) {
  for (const p of currentPolygons) {
    if (pointInPolygon(imgX, imgY, p.points)) return p;
  }
  return null;
}

/** Convert client (mouse) coords → image pixel coords via OSD viewport */
function clientToImageCoord(clientX: number, clientY: number): OpenSeadragon.Point | null {
  if (!viewer) return null;
  const rect = viewer.container.getBoundingClientRect();
  const vp = new OpenSeadragon.Point(clientX - rect.left, clientY - rect.top);
  return viewer.viewport.viewerElementToImageCoordinates(vp);
}

// ---------------------------------------------------------------------------
// Konva ↔ OSD sync
// ---------------------------------------------------------------------------

function requestSync() {
  if (!syncRequested) {
    syncRequested = true;
    requestAnimationFrame(() => {
      syncKonva();
      syncRequested = false;
    });
  }
}

function syncKonva() {
  if (!viewer || !stage || !layer || !viewer.viewport || !viewer.isOpen()) return;

  const cw = viewer.container.clientWidth;
  const ch = viewer.container.clientHeight;
  stage.width(cw);
  stage.height(ch);

  const tiledImage = viewer.world.getItemAt(0);
  if (!tiledImage) return;

  const bounds = viewer.viewport.getBounds();
  const zoom = viewer.viewport.getZoom();
  const imageSize = tiledImage.getContentSize();

  // image-pixel → screen-pixel scale
  const scale = (1 / imageSize.x) * (cw * zoom);

  // offset: where image origin (0,0) maps to in screen pixels
  const offsetX = -bounds.x * (cw * zoom);
  const offsetY = -bounds.y * (cw * zoom);

  stage.scale({ x: scale, y: scale });
  stage.position({ x: offsetX, y: offsetY });
  layer.draw();
}

// ---------------------------------------------------------------------------
// Overlay management
// ---------------------------------------------------------------------------

function createKonvaOverlay(alto: PageAltoData) {
  if (!layer) return;

  console.log(`[Konva] Creating overlay: ${alto.textLines.length} text lines`);

  layer.destroyChildren();
  shapeMap.clear();
  currentPolygons = [];

  for (const line of alto.textLines) {
    const points = parsePolygonPoints(line.polygon);
    if (points.length < 6) continue;

    currentPolygons.push({ lineId: line.id, points, line });

    const shape = new Konva.Line({
      points,
      closed: true,
      fill: "rgba(193, 95, 60, 0.15)",
      stroke: "rgba(193, 95, 60, 0.7)",
      strokeWidth: 2,
      listening: false,
    });
    shapeMap.set(line.id, shape);
    layer.add(shape);
  }

  updateOverlayVisibility();
  syncKonva();
}

function updateOverlayVisibility() {
  if (layer) {
    layer.visible(overlaysVisible);
    layer.draw();
  }
}

function highlightShape(lineId: string | null) {
  if (!layer) return;

  if (highlightedLineId) {
    const prev = shapeMap.get(highlightedLineId);
    if (prev) {
      prev.fill("rgba(193, 95, 60, 0.15)");
      prev.stroke("rgba(193, 95, 60, 0.7)");
      prev.strokeWidth(2);
    }
  }

  if (lineId) {
    const s = shapeMap.get(lineId);
    if (s) {
      s.fill("rgba(193, 95, 60, 0.3)");
      s.stroke("rgba(193, 95, 60, 1)");
      s.strokeWidth(3);
    }
  }

  highlightedLineId = lineId;
  layer.batchDraw();
}

// ---------------------------------------------------------------------------
// Page loading
// ---------------------------------------------------------------------------

async function loadPage(pageIndex: number) {
  if (!viewer) return;

  currentAlto = null;
  currentPolygons = [];
  if (layer) {
    layer.destroyChildren();
    shapeMap.clear();
    layer.draw();
  }

  try {
    // 1. Load image bytes from server → blob URL
    const blobUrl = await loadImageBytes(data.imageUrls[pageIndex]);

    // 2. Open blob URL in OSD (no network requests — local data)
    viewer.open({ type: "image", url: blobUrl, buildPyramid: false } as any);

    // 3. After OSD opens, load ALTO from server
    const onOpen = async () => {
      viewer?.removeHandler("open", onOpen);
      try {
        const alto = await loadAlto(data.altoUrls[pageIndex]);
        currentAlto = alto;
        createKonvaOverlay(alto);
        pageStatus = `${alto.textLines.length} text lines`;
        setTimeout(() => (pageStatus = ""), 3000);
      } catch (e) {
        console.error("[ALTO] Failed:", e);
        currentAlto = { textLines: [], pageWidth: 0, pageHeight: 0 };
        pageStatus = "Text overlay unavailable";
      }
    };
    viewer.addHandler("open", onOpen);
  } catch (e) {
    console.error("[loadPage] Failed:", e);
    pageStatus = `Error: ${e instanceof Error ? e.message : String(e)}`;
  }
}

function goToPage(index: number) {
  if (index < 0 || index >= totalPages) return;
  currentPageIndex = index;
  loadPage(index);
}

function toggleOverlays() {
  overlaysVisible = !overlaysVisible;
  updateOverlayVisibility();
}

// ---------------------------------------------------------------------------
// Mouse interaction (on OSD container, Konva canvas is pointer-events:none)
// ---------------------------------------------------------------------------

function handleMouseDown(e: MouseEvent) {
  mouseDownPos = { x: e.clientX, y: e.clientY };
}

function handleMouseMove(e: MouseEvent) {
  if (!overlaysVisible || !currentAlto?.textLines.length) {
    if (tooltip) { tooltip = null; highlightShape(null); }
    return;
  }
  const img = clientToImageCoord(e.clientX, e.clientY);
  if (!img) return;

  const hit = findLineAtImageCoord(img.x, img.y);
  if (hit) {
    tooltip = { text: hit.line.transcription, x: e.clientX + 15, y: e.clientY + 15 };
    if (highlightedLineId !== hit.lineId) highlightShape(hit.lineId);
    if (viewer) viewer.canvas.style.cursor = "pointer";
  } else {
    if (tooltip) { tooltip = null; highlightShape(null); }
    if (viewer) viewer.canvas.style.cursor = "";
  }
}

function handleClick(e: MouseEvent) {
  if (!overlaysVisible || !currentAlto?.textLines.length) return;
  if (mouseDownPos) {
    const dx = e.clientX - mouseDownPos.x;
    const dy = e.clientY - mouseDownPos.y;
    if (dx * dx + dy * dy > 25) return; // was a drag
  }
  const img = clientToImageCoord(e.clientX, e.clientY);
  if (!img) return;

  const hit = findLineAtImageCoord(img.x, img.y);
  if (hit) sendLineText(hit.line);
}

function handleMouseLeave() {
  tooltip = null;
  highlightShape(null);
  if (viewer) viewer.canvas.style.cursor = "";
}

async function sendLineText(line: TextLine) {
  status = "Sending selected text...";
  try {
    await app.sendMessage({
      role: "user",
      content: [{ type: "text", text: `[Page ${currentPageIndex + 1}] ${line.id}: ${line.transcription}` }],
    });
    status = "Text sent for translation";
  } catch (e) {
    console.error(e);
    status = "Failed to send text";
  } finally {
    setTimeout(() => (status = ""), 2000);
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMount(() => {
  console.log("[DocumentViewer] onMount:", data.imageUrls.length, "pages");

  // Initialize OSD (empty — no tile source yet, loadPage will open one)
  viewer = new OpenSeadragon.Viewer({
    element: osdContainer,
    showNavigationControl: false,
    gestureSettingsMouse: { clickToZoom: false },
    prefixUrl: "",
    maxZoomPixelRatio: 4,
    minZoomLevel: 0.5,
    visibilityRatio: 0.5,
  });

  // Create Konva container inside OSD's canvas element
  konvaDiv = document.createElement("div");
  konvaDiv.style.position = "absolute";
  konvaDiv.style.top = "0";
  konvaDiv.style.left = "0";
  konvaDiv.style.width = "100%";
  konvaDiv.style.height = "100%";
  konvaDiv.style.pointerEvents = "none";
  viewer.canvas.appendChild(konvaDiv);

  const cw = viewer.container.clientWidth;
  const ch = viewer.container.clientHeight;
  stage = new Konva.Stage({
    container: konvaDiv,
    width: cw || 800,
    height: ch || 600,
    listening: false,
  });
  layer = new Konva.Layer();
  stage.add(layer);

  // Viewport sync
  viewer.addHandler("animation", requestSync);
  viewer.addHandler("animation-finish", syncKonva);
  viewer.addHandler("open", syncKonva);
  viewer.addHandler("resize", syncKonva);

  // OSD lifecycle logging
  viewer.addHandler("open", () => console.log("[OSD] 'open' event — image loaded"));
  viewer.addHandler("open-failed", (event: any) => console.error("[OSD] 'open-failed':", event));

  // Container resize
  resizeObserver = new ResizeObserver(() => syncKonva());
  resizeObserver.observe(viewer.container);

  // Mouse interaction
  const el = viewer.container;
  el.addEventListener("mousedown", handleMouseDown);
  el.addEventListener("mousemove", handleMouseMove);
  el.addEventListener("click", handleClick);
  el.addEventListener("mouseleave", handleMouseLeave);

  // Load first page
  loadPage(0);
});

onDestroy(() => {
  const el = viewer?.container;
  el?.removeEventListener("mousedown", handleMouseDown);
  el?.removeEventListener("mousemove", handleMouseMove);
  el?.removeEventListener("click", handleClick);
  el?.removeEventListener("mouseleave", handleMouseLeave);
  resizeObserver?.disconnect();
  stage?.destroy();
  konvaDiv?.remove();
  viewer?.destroy();

  // Clean up blob URLs
  for (const url of blobUrls) {
    URL.revokeObjectURL(url);
  }
});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="viewer-wrapper" class:fullscreen={displayMode === "fullscreen"}>
  <!-- Controls -->
  <div class="controls">
    <button class="control-btn" class:active={overlaysVisible} onclick={toggleOverlays}>
      {overlaysVisible ? "Hide Overlays" : "Show Overlays"}
    </button>

    {#if totalPages > 1}
      <div class="page-nav">
        <button class="control-btn" onclick={() => goToPage(currentPageIndex - 1)} disabled={currentPageIndex === 0}>
          Prev
        </button>
        <span class="page-indicator">
          Page {currentPageIndex + 1} / {totalPages}
        </span>
        <button class="control-btn" onclick={() => goToPage(currentPageIndex + 1)} disabled={currentPageIndex === totalPages - 1}>
          Next
        </button>
      </div>
    {/if}

    {#if pageStatus}
      <span class="page-status">{pageStatus}</span>
    {/if}
  </div>

  <!-- OpenSeadragon (Konva canvas injected inside via JS) -->
  <div class="osd-container" bind:this={osdContainer}></div>

  <!-- Status -->
  {#if status}
    <p class="status">{status}</p>
  {/if}
</div>

<!-- Tooltip (fixed-position, follows mouse) -->
{#if tooltip && tooltip.x > 0}
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
.page-nav {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs, 0.25rem);
}
.page-indicator {
  font-size: var(--font-text-sm-size, 0.875rem);
  color: var(--color-text-secondary);
  white-space: nowrap;
  min-width: 80px;
  text-align: center;
}
.page-status {
  font-size: var(--font-text-sm-size, 0.875rem);
  color: var(--color-text-secondary);
  margin-left: auto;
}

/* Buttons */
.control-btn {
  padding: var(--spacing-sm, 0.5rem) var(--spacing-md, 1rem);
  min-width: 80px;
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

/* OSD Container */
.osd-container {
  width: 100%;
  flex: 1;
  background: var(--color-background-secondary, #f5f5f5);
  border-radius: var(--border-radius-lg, 10px);
  border: 1px solid var(--color-border-primary);
  overflow: hidden;
  min-height: 400px;
  position: relative;
}

/* Tooltip */
.tooltip {
  position: fixed;
  background: var(--color-tooltip-background, #333);
  color: var(--color-tooltip-text, #fff);
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
