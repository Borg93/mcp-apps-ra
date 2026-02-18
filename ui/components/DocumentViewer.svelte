<script lang="ts">
import { onMount, onDestroy } from "svelte";
import type { App } from "@modelcontextprotocol/ext-apps";
import type { TextLine, ViewerData, PageData, PageAltoData, TooltipState } from "../lib/types";
import type { PolygonHit } from "../lib/geometry";
import { buildPolygonHits, findHitAtImageCoord, screenToImage } from "../lib/geometry";
import { parsePageResult } from "../lib/utils";

interface Props {
  app: App;
  data: ViewerData;
  currentPageIndex: number;
  onPageChange: (index: number) => void;
}

let { app, data, currentPageIndex, onPageChange }: Props = $props();

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MIN_SCALE = 0.1;
const MAX_SCALE = 10;
const ZOOM_SPEED = 0.003;
const ZOOM_LERP = 0.25;
const PAN_FRICTION = 0.92;

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let tooltip = $state<TooltipState | null>(null);
let highlightedLineId = $state<string | null>(null);

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
let currentPolygons: PolygonHit[] = [];

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

  const img = screenToImage(cx, cy, transform);
  const hit = findHitAtImageCoord(img.x, img.y, currentPolygons);
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
  const img = screenToImage(cx, cy, transform);
  const hit = findHitAtImageCoord(img.x, img.y, currentPolygons);
  if (hit) sendLineText(hit.line);
}

function applyPanInertia() {
  function step() {
    panVelocity.vx *= PAN_FRICTION;
    panVelocity.vy *= PAN_FRICTION;

    const speed = Math.sqrt(panVelocity.vx ** 2 + panVelocity.vy ** 2);
    if (speed < 0.02) { // px/ms — stop when negligible
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

  const factor = Math.exp(delta * ZOOM_SPEED);

  targetScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, targetScale * factor));

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

  const newScale = transform.scale + diff * ZOOM_LERP;
  applyZoom(newScale);

  requestAnimationFrame(animateZoom);
}

function applyZoom(newScale: number) {
  const clamped = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
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
  currentPolygons = currentAlto?.textLines ? buildPolygonHits(currentAlto.textLines) : [];
  highlightedLineId = null;
  tooltip = null;

  const img = new Image();
  img.onload = () => {
    image = img;
    fitToCanvas();
    draw();
    updatePageContext();
  };
  img.onerror = () => {
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

  const page = await fetchPageData(index);
  if (page && currentPageIndex === index) {
    renderPage(page);
    prefetchAdjacentPages(index);
  }
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
  const lines = currentAlto?.textLines ?? [];
  const fullText = lines.map(l => l.transcription).join("\n");

  try {
    await app.updateModelContext({
      content: [{
        type: "text",
        text: [
          `Document viewer: page ${page}/${totalPages}`,
          fullText
            ? `Full page transcription:\n${fullText}`
            : "(no transcribed text on this page)",
        ].join("\n"),
      }],
    });
  } catch (e) {
    console.error("[updateModelContext]", e);
  }
}

async function sendLineText(line: TextLine) {
  try {
    await app.sendMessage({
      role: "user",
      content: [{ type: "text", text: `I selected this text on page ${currentPageIndex + 1}: "${line.transcription}"\nPlease translate or explain this text in context of the full page.` }],
    });
  } catch (e) {
    console.error("sendLineText failed:", e);
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
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
