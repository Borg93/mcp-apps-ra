<script lang="ts">
import { onMount, onDestroy } from "svelte";
import OpenSeadragon from "openseadragon";
import { createOSDAnnotator } from "@annotorious/openseadragon";
import "@annotorious/openseadragon/annotorious-openseadragon.css";

import type { App } from "@modelcontextprotocol/ext-apps";
import type { PageData, TextLine, TooltipState, ViewerData } from "../lib/types";
import { textLinesToAnnotations } from "../lib/annotations";
import { isManifestData } from "../lib/utils";

interface Props {
  app: App;
  data: ViewerData;
  displayMode?: "inline" | "fullscreen";
}

let { app, data, displayMode = "inline" }: Props = $props();

// State
let overlaysVisible = $state(true);
let currentPageIndex = $state(0);
let tooltip = $state<TooltipState | null>(null);
let status = $state("");
let osdContainer: HTMLDivElement;

// Derived
let pages = $derived(data.pages);
let currentPage = $derived(pages[currentPageIndex]);
let title = $derived(isManifestData(data) ? data.title : undefined);

// OSD + Annotorious instances
let viewer: OpenSeadragon.Viewer | null = null;
let annotator: ReturnType<typeof createOSDAnnotator> | null = null;

// Map annotation IDs back to TextLine data
let lineMap = new Map<string, TextLine>();

function buildLineMap(textLines: TextLine[]) {
  lineMap.clear();
  for (const line of textLines) {
    lineMap.set(line.id, line);
  }
}

function getTileSource(page: PageData): OpenSeadragon.TileSourceOptions | object {
  if (page.imageService) {
    // IIIF tile source - OSD can consume the service config directly
    return page.imageService as object;
  }
  // Simple image URL fallback
  return {
    type: "image",
    url: page.imageUrl,
    buildPyramid: false,
  };
}

function loadPage(page: PageData) {
  if (!viewer || !annotator) return;

  // Clear existing annotations
  annotator.clearAnnotations();

  // Swap tile source
  viewer.open(getTileSource(page) as OpenSeadragon.TileSourceOptions);

  // Build line map and add annotations after tiles load
  buildLineMap(page.textLines);

  const handler = () => {
    if (!annotator) return;
    const annotations = textLinesToAnnotations(page.textLines);
    for (const anno of annotations) {
      annotator.addAnnotation(anno);
    }
    // Apply visibility
    annotator.setVisible(overlaysVisible);
    viewer?.removeHandler("open", handler);
  };
  viewer.addHandler("open", handler);
}

function goToPage(index: number) {
  if (index < 0 || index >= pages.length) return;
  currentPageIndex = index;
  loadPage(pages[index]);
}

function toggleOverlays() {
  overlaysVisible = !overlaysVisible;
  if (annotator) {
    annotator.setVisible(overlaysVisible);
  }
}

async function sendLineText(line: TextLine) {
  status = "Sending selected text...";
  try {
    await app.sendMessage({
      role: "user",
      content: [
        {
          type: "text",
          text: `[Page ${currentPage.pageNumber}] ${line.id}: ${line.transcription}`,
        },
      ],
    });
    status = "Text sent for translation";
  } catch (e) {
    console.error(e);
    status = "Failed to send text";
  } finally {
    setTimeout(() => (status = ""), 2000);
  }
}

onMount(() => {
  viewer = new OpenSeadragon.Viewer({
    element: osdContainer,
    showNavigationControl: false,
    gestureSettingsMouse: { clickToZoom: false },
    crossOriginPolicy: "Anonymous",
    prefixUrl: "",
    tileSources: getTileSource(pages[0]) as OpenSeadragon.TileSourceOptions,
    maxZoomPixelRatio: 4,
    minZoomLevel: 0.5,
    visibilityRatio: 0.5,
  });

  annotator = createOSDAnnotator(viewer, {
    drawingEnabled: false,
  });

  // Style annotations with the orange theme
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  annotator.setStyle((_annotation: any, state?: any) => {
    if (state?.selected) {
      return {
        fill: "#A14A2F",
        fillOpacity: 0.35,
        stroke: "#A14A2F",
        strokeWidth: 3,
      };
    }
    if (state?.hovered) {
      return {
        fill: "#C15F3C",
        fillOpacity: 0.3,
        stroke: "#C15F3C",
        strokeWidth: 3,
      };
    }
    return {
      fill: "#C15F3C",
      fillOpacity: 0.15,
      stroke: "#C15F3C",
      strokeOpacity: 0.7,
      strokeWidth: 2,
    };
  });

  // Click annotation -> send text
  annotator.on("clickAnnotation", (annotation: any) => {
    const line = lineMap.get(annotation.id);
    if (line) sendLineText(line);
  });

  // Hover -> tooltip
  annotator.on("mouseEnterAnnotation", (annotation: any) => {
    const line = lineMap.get(annotation.id);
    if (line) {
      // Position tooltip near center of page - will update on mouse move
      tooltip = { text: line.transcription, x: 0, y: 0 };
    }
  });

  annotator.on("mouseLeaveAnnotation", () => {
    tooltip = null;
  });

  // Load annotations for first page once tiles are ready
  buildLineMap(pages[0].textLines);
  viewer.addOnceHandler("open", () => {
    if (!annotator) return;
    const annotations = textLinesToAnnotations(pages[0].textLines);
    for (const anno of annotations) {
      annotator.addAnnotation(anno);
    }
  });
});

onDestroy(() => {
  annotator?.destroy();
  viewer?.destroy();
});

function handleContainerMouseMove(e: MouseEvent) {
  if (tooltip) {
    tooltip = { ...tooltip, x: e.clientX + 15, y: e.clientY + 15 };
  }
}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
  class="viewer-wrapper"
  class:fullscreen={displayMode === "fullscreen"}
  onmousemove={handleContainerMouseMove}
>
  <!-- Header -->
  <div class="controls">
    {#if title}
      <span class="title">{title}</span>
    {/if}

    <button
      class="control-btn"
      class:active={overlaysVisible}
      onclick={toggleOverlays}
    >
      {overlaysVisible ? "Hide Overlays" : "Show Overlays"}
    </button>

    {#if pages.length > 1}
      <div class="page-nav">
        <button
          class="control-btn"
          onclick={() => goToPage(currentPageIndex - 1)}
          disabled={currentPageIndex === 0}
        >
          Prev
        </button>
        <span class="page-indicator">
          {currentPage.label} ({currentPageIndex + 1} / {pages.length})
        </span>
        <button
          class="control-btn"
          onclick={() => goToPage(currentPageIndex + 1)}
          disabled={currentPageIndex === pages.length - 1}
        >
          Next
        </button>
      </div>
    {/if}
  </div>

  <!-- OpenSeadragon container -->
  <div class="osd-container" bind:this={osdContainer}></div>

  <!-- Status -->
  {#if status}
    <p class="status">{status}</p>
  {/if}
</div>

<!-- Tooltip -->
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

.title {
  font-size: var(--font-text-sm-size, 0.875rem);
  font-weight: 500;
  color: var(--color-text-primary);
  margin-right: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
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
  background: var(--color-svg-background);
  border-radius: var(--border-radius-lg, 10px);
  border: 1px solid var(--color-border-primary);
  overflow: hidden;
  min-height: 400px;
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
