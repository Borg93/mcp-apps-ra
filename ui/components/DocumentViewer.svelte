<script lang="ts">
import { onMount, onDestroy } from "svelte";
import type { App } from "@modelcontextprotocol/ext-apps";
import type { TextLine, ViewerData, PageData, PageAltoData, TooltipState } from "../lib/types";
import { parsePageResult } from "../lib/utils";

interface Props {
  app: App;
  data: ViewerData;
  currentPageIndex: number;
  onPageChange: (index: number) => void;
}

let { app, data, currentPageIndex, onPageChange }: Props = $props();

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let tooltip = $state<TooltipState | null>(null);
let highlightedLineId = $state<string | null>(null);
let status = $state("");
let loading = $state(false);

let totalPages = $derived(data.pageUrls.length);

// Client-side page cache — each page fetched at most once
let pageCache = new Map<number, PageData>();

// Canvas + transform
let canvasEl: HTMLCanvasElement;
let containerEl: HTMLDivElement;
let wrapperEl: HTMLDivElement;
let image: HTMLImageElement | null = null;
let transform = { x: 0, y: 0, scale: 1 };

// Current page ALTO data
let currentAlto: PageAltoData | null = null;

// Parsed polygon data for hit testing (image coordinates)
let currentPolygons: { lineId: string; points: number[]; line: TextLine }[] = [];

// Pointer state for pan + click detection
let pointerDown: { x: number; y: number; tx: number; ty: number } | null = null;
let dragged = false;
let panVelocity = { vx: 0, vy: 0 };
let lastPointerPos = { x: 0, y: 0, t: 0 };
let panInertiaId = 0;

// Smooth zoom animation state
let targetScale = 1;
let zoomAnimating = false;
let zoomCenterX = 0;
let zoomCenterY = 0;

// Animation frame handle
let rafId = 0;

// Visibility-aware rendering (pause when off-screen)
let isVisible = true;
let pendingDraw = false;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Parse ALTO polygon "x1,y1 x2,y2 ..." into flat [x1,y1,x2,y2,...] */
function parsePolygonPoints(polygon: string): number[] {
  const pts: number[] = [];
  for (const pair of polygon.trim().split(/\s+/)) {
    const [x, y] = pair.split(",").map(Number);
    if (!isNaN(x) && !isNaN(y)) pts.push(x, y);
  }
  return pts;
}

/** Ray-casting point-in-polygon test */
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

/** Convert screen (canvas-relative) coords to image pixel coords */
function screenToImage(sx: number, sy: number): { x: number; y: number } {
  return {
    x: (sx - transform.x) / transform.scale,
    y: (sy - transform.y) / transform.scale,
  };
}

// ---------------------------------------------------------------------------
// Drawing
// ---------------------------------------------------------------------------

function draw() {
  if (!canvasEl || !image) return;
  const ctx = canvasEl.getContext("2d");
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const w = canvasEl.clientWidth;
  const h = canvasEl.clientHeight;

  if (canvasEl.width !== w * dpr || canvasEl.height !== h * dpr) {
    canvasEl.width = w * dpr;
    canvasEl.height = h * dpr;
  }

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);

  ctx.save();
  ctx.translate(transform.x, transform.y);
  ctx.scale(transform.scale, transform.scale);

  ctx.drawImage(image, 0, 0);

  if (currentPolygons.length > 0) {
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

  ctx.restore();
}

function requestDraw() {
  if (!isVisible) {
    pendingDraw = true;
    return;
  }
  if (!rafId) {
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      draw();
    });
  }
}

function fitToCanvas() {
  if (!image || !canvasEl) return;
  const cw = canvasEl.clientWidth;
  const ch = canvasEl.clientHeight;
  if (cw === 0 || ch === 0) return;
  const padding = 8;
  const scaleX = (cw - padding * 2) / image.naturalWidth;
  const scaleY = (ch - padding * 2) / image.naturalHeight;
  // Allow scaling UP to fill the canvas, not just down
  transform.scale = Math.min(scaleX, scaleY);
  transform.x = (cw - image.naturalWidth * transform.scale) / 2;
  transform.y = (ch - image.naturalHeight * transform.scale) / 2;
  // Sync smooth zoom target so next scroll starts from fitted scale
  targetScale = transform.scale;
}

// ---------------------------------------------------------------------------
// Pointer interaction (pan + click + hover)
// ---------------------------------------------------------------------------

function handlePointerDown(e: PointerEvent) {
  if (e.button !== 0) return;
  // Cancel any ongoing inertia animation
  if (panInertiaId) { cancelAnimationFrame(panInertiaId); panInertiaId = 0; }
  pointerDown = { x: e.clientX, y: e.clientY, tx: transform.x, ty: transform.y };
  dragged = false;
  panVelocity = { vx: 0, vy: 0 };
  lastPointerPos = { x: e.clientX, y: e.clientY, t: performance.now() };
  canvasEl.setPointerCapture(e.pointerId);
}

function handlePointerMove(e: PointerEvent) {
  const rect = canvasEl.getBoundingClientRect();
  const cx = e.clientX - rect.left;
  const cy = e.clientY - rect.top;

  if (pointerDown) {
    const dx = e.clientX - pointerDown.x;
    const dy = e.clientY - pointerDown.y;
    if (dx * dx + dy * dy > 9) dragged = true;
    transform.x = pointerDown.tx + dx;
    transform.y = pointerDown.ty + dy;

    // Track velocity for inertia
    const now = performance.now();
    const dt = now - lastPointerPos.t;
    if (dt > 0) {
      panVelocity.vx = (e.clientX - lastPointerPos.x) / dt;
      panVelocity.vy = (e.clientY - lastPointerPos.y) / dt;
    }
    lastPointerPos = { x: e.clientX, y: e.clientY, t: now };

    requestDraw();
    return;
  }

  if (!currentPolygons.length) {
    if (tooltip) { tooltip = null; highlightedLineId = null; requestDraw(); }
    return;
  }

  const img = screenToImage(cx, cy);
  const hit = findLineAtImageCoord(img.x, img.y);
  if (hit) {
    tooltip = { text: hit.line.transcription, x: e.clientX + 15, y: e.clientY + 15 };
    if (highlightedLineId !== hit.lineId) {
      highlightedLineId = hit.lineId;
      requestDraw();
    }
    canvasEl.style.cursor = "pointer";
  } else {
    if (tooltip) {
      tooltip = null;
      highlightedLineId = null;
      requestDraw();
    }
    canvasEl.style.cursor = pointerDown ? "grabbing" : "grab";
  }
}

function handlePointerUp(e: PointerEvent) {
  if (!pointerDown) return;
  const wasDrag = dragged;
  pointerDown = null;
  canvasEl.releasePointerCapture(e.pointerId);

  if (wasDrag) {
    // Apply inertia if velocity is meaningful
    const speed = Math.sqrt(panVelocity.vx ** 2 + panVelocity.vy ** 2);
    if (speed > 0.1) {
      applyPanInertia();
    }
    return;
  }

  if (!currentPolygons.length) return;
  const rect = canvasEl.getBoundingClientRect();
  const cx = e.clientX - rect.left;
  const cy = e.clientY - rect.top;
  const img = screenToImage(cx, cy);
  const hit = findLineAtImageCoord(img.x, img.y);
  if (hit) sendLineText(hit.line);
}

function applyPanInertia() {
  const FRICTION = 0.92; // Deceleration per frame
  const MIN_SPEED = 0.3; // Stop threshold (px/frame)

  function step() {
    panVelocity.vx *= FRICTION;
    panVelocity.vy *= FRICTION;

    const speed = Math.sqrt(panVelocity.vx ** 2 + panVelocity.vy ** 2);
    if (speed < MIN_SPEED / 16) { // velocity is in px/ms, scale threshold
      panInertiaId = 0;
      return;
    }

    // velocity is px/ms, multiply by ~16ms frame time
    transform.x += panVelocity.vx * 16;
    transform.y += panVelocity.vy * 16;
    draw();
    panInertiaId = requestAnimationFrame(step);
  }

  panInertiaId = requestAnimationFrame(step);
}

function handlePointerLeave() {
  tooltip = null;
  if (highlightedLineId) {
    highlightedLineId = null;
    requestDraw();
  }
}

function handleWheel(e: WheelEvent) {
  e.preventDefault();
  const rect = canvasEl.getBoundingClientRect();
  zoomCenterX = e.clientX - rect.left;
  zoomCenterY = e.clientY - rect.top;

  // Normalize deltaY across input devices:
  // - Mouse wheel: deltaMode=0 (pixels), large values (~100)
  // - Trackpad pinch: deltaMode=0 (pixels), small values (~1-10)
  // - Old-style wheel: deltaMode=1 (lines)
  let delta = -e.deltaY;
  if (e.deltaMode === 1) delta *= 20; // line mode → approximate pixels

  // Gentle zoom speed — small multiplier so trackpad feels smooth
  const ZOOM_SPEED = 0.003;
  const factor = Math.exp(delta * ZOOM_SPEED);

  targetScale = Math.max(0.1, Math.min(10, targetScale * factor));

  if (!zoomAnimating) {
    zoomAnimating = true;
    animateZoom();
  }
}

function animateZoom() {
  if (!zoomAnimating) return;

  const diff = targetScale - transform.scale;

  // Close enough — snap and stop
  if (Math.abs(diff) < 0.001) {
    applyZoom(targetScale);
    zoomAnimating = false;
    return;
  }

  // Ease toward target (lerp factor 0.25 = smooth but responsive)
  const newScale = transform.scale + diff * 0.25;
  applyZoom(newScale);

  requestAnimationFrame(animateZoom);
}

function applyZoom(newScale: number) {
  const clamped = Math.max(0.1, Math.min(10, newScale));
  const ratio = clamped / transform.scale;
  transform.x = zoomCenterX - (zoomCenterX - transform.x) * ratio;
  transform.y = zoomCenterY - (zoomCenterY - transform.y) * ratio;
  transform.scale = clamped;
  draw(); // Draw immediately inside animation loop (no RAF scheduling needed)
}

// ---------------------------------------------------------------------------
// Page rendering + navigation
// ---------------------------------------------------------------------------

/** Render a PageData that's already available */
function renderPage(page: PageData) {
  currentAlto = page.alto;
  currentPolygons = [];
  highlightedLineId = null;
  tooltip = null;

  if (currentAlto?.textLines) {
    for (const line of currentAlto.textLines) {
      const points = parsePolygonPoints(line.polygon);
      if (points.length >= 6) {
        currentPolygons.push({ lineId: line.id, points, line });
      }
    }
  }

  const img = new Image();
  img.onload = () => {
    image = img;
    fitToCanvas();
    draw();
    status = currentPolygons.length > 0
      ? `Page ${currentPageIndex + 1} / ${totalPages} — ${currentPolygons.length} text lines`
      : `Page ${currentPageIndex + 1} / ${totalPages}`;
    updatePageContext();
  };
  img.onerror = () => {
    status = "Failed to load image";
    image = null;
    draw();
  };
  img.src = page.imageDataUrl;
}

/** Fetch page ALTO data from server (image loads directly via URL) */
async function fetchPageData(index: number): Promise<PageData | null> {
  if (index < 0 || index >= totalPages) return null;
  if (pageCache.has(index)) return pageCache.get(index)!;

  try {
    const urls = data.pageUrls[index];
    const result = await app.callServerTool({
      name: "load-page",
      arguments: {
        image_url: urls.image,
        alto_url: urls.alto,
        page_index: index,
      },
    });

    if (result.isError) {
      const errText = result.content?.map((c: any) => ("text" in c ? c.text : "")).join(" ") ?? "Unknown error";
      console.error("load-page error:", errText);
      return null;
    }

    const page = parsePageResult(result);
    if (page) {
      pageCache.set(index, page);
      return page;
    }
  } catch (e) {
    console.error("load-page failed:", e);
  }
  return null;
}

/** Fetch and render a page — use cache or fetch ALTO via callServerTool */
async function fetchAndRenderPage(index: number) {
  if (index < 0 || index >= totalPages) return;

  // Check cache first — instant render, no server call
  const cached = pageCache.get(index);
  if (cached) {
    renderPage(cached);
    prefetchAdjacentPages(index);
    return;
  }

  // Fetch ALTO from server (image loads directly in browser via URL)
  loading = true;
  status = `Loading page ${index + 1}...`;

  const page = await fetchPageData(index);
  if (page && currentPageIndex === index) {
    renderPage(page);
    prefetchAdjacentPages(index);
  } else if (!page) {
    status = `Failed to load page ${index + 1}`;
  }
  loading = false;
}

/** Prefetch ALTO data for adjacent pages so navigation feels instant */
function prefetchAdjacentPages(index: number) {
  const neighbors = [index - 1, index + 1];
  for (const n of neighbors) {
    if (n >= 0 && n < totalPages && !pageCache.has(n)) {
      // Fire and forget — don't await, don't block rendering
      fetchPageData(n);
    }
  }
}

// ---------------------------------------------------------------------------
// Model context + text selection
// ---------------------------------------------------------------------------

async function updatePageContext() {
  if (!app) return;
  const page = currentPageIndex + 1;
  const lineCount = currentAlto?.textLines?.length ?? 0;
  const sampleLines = currentAlto?.textLines
    ?.slice(0, 5)
    .map(l => l.transcription)
    .join("\n") ?? "";

  try {
    await app.updateModelContext({
      content: [{
        type: "text",
        text: [
          `Document viewer: page ${page}/${totalPages}`,
          lineCount > 0 ? `${lineCount} transcribed text lines.` : "No transcribed text.",
          sampleLines ? `First lines:\n${sampleLines}` : "",
        ].filter(Boolean).join("\n"),
      }],
    });
  } catch (e) {
    console.error("[updateModelContext]", e);
  }
}

async function sendLineText(line: TextLine) {
  status = "Sending selected text...";
  try {
    await app.sendMessage({
      role: "user",
      content: [{ type: "text", text: `Selected text from page ${currentPageIndex + 1}/${totalPages}:\n"${line.transcription}"` }],
    });
    status = "Text sent";
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

// Watch for page index changes from parent (thumbnail clicks)
let lastRenderedIndex = -1;
$effect(() => {
  const idx = currentPageIndex;
  if (idx !== lastRenderedIndex) {
    lastRenderedIndex = idx;
    fetchAndRenderPage(idx);
  }
});

let resizeObserver: ResizeObserver | null = null;
let visibilityObserver: IntersectionObserver | null = null;

onMount(() => {
  resizeObserver = new ResizeObserver(() => {
    if (image) {
      fitToCanvas();
      draw();
    }
  });
  resizeObserver.observe(containerEl);

  // Pause canvas rendering when scrolled out of view
  visibilityObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      isVisible = entry.isIntersecting;
      if (isVisible && pendingDraw) {
        pendingDraw = false;
        requestDraw();
      }
    }
  });
  visibilityObserver.observe(wrapperEl);

  // Seed cache with first page from initial data
  pageCache.set(0, data.firstPage);
});

onDestroy(() => {
  resizeObserver?.disconnect();
  visibilityObserver?.disconnect();
  if (rafId) cancelAnimationFrame(rafId);
  if (panInertiaId) cancelAnimationFrame(panInertiaId);
  zoomAnimating = false;
});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="viewer-wrapper" bind:this={wrapperEl}>
  <!-- Status bar -->
  {#if status}
    <div class="status-bar">
      <span class="status-text">{status}</span>
    </div>
  {/if}

  <!-- Canvas -->
  <div class="canvas-container" bind:this={containerEl}>
    <canvas
      bind:this={canvasEl}
      style="cursor: grab"
      onpointerdown={handlePointerDown}
      onpointermove={handlePointerMove}
      onpointerup={handlePointerUp}
      onpointerleave={handlePointerLeave}
      onwheel={handleWheel}
    ></canvas>
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
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.status-bar {
  padding: var(--spacing-xs, 0.25rem) var(--spacing-sm, 0.5rem);
  background: var(--color-background-secondary, #f5f5f5);
  border-bottom: 1px solid var(--color-border-primary);
}
.status-text {
  font-size: var(--font-text-sm-size, 0.875rem);
  color: var(--color-text-secondary);
}

.canvas-container {
  flex: 1;
  background: var(--color-background-secondary, #f5f5f5);
  overflow: hidden;
  position: relative;
}
.canvas-container canvas {
  display: block;
  width: 100%;
  height: 100%;
}

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
</style>
