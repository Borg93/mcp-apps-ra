<script lang="ts">
import { onMount, onDestroy } from "svelte";
import type { App } from "@modelcontextprotocol/ext-apps";
import type { ViewerData } from "../lib/types";
import { parseThumbnailResult } from "../lib/utils";

interface Props {
  app: App;
  data: ViewerData;
  currentPageIndex: number;
  onPageSelect: (index: number) => void;
}

let { app, data, currentPageIndex, onPageSelect }: Props = $props();

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let totalPages = $derived(data.pageUrls.length);

// Cache: page index → thumbnail data URL
let thumbnailCache = new Map<number, string>();

// Tracks which thumbnails have been rendered (triggers reactivity)
let loadedIndices = $state(new Set<number>());

// Container ref for scrolling
let containerEl: HTMLDivElement;

// Refs for placeholder elements (for IntersectionObserver)
let placeholderEls: HTMLDivElement[] = [];

// Batch loading state
let pendingIndices = new Set<number>();
let requestedIndices = new Set<number>(); // tracks all requested indices to prevent duplicates
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let batchInFlight = false;
let batchQueue: number[] = [];
let destroyed = false;

// ---------------------------------------------------------------------------
// Batch fetching
// ---------------------------------------------------------------------------

async function fetchBatch(indices: number[]) {
  if (indices.length === 0 || destroyed) return;
  batchInFlight = true;

  try {
    const imageUrls = indices.map(i => data.pageUrls[i].image);
    const result = await app.callServerTool({
      name: "load-thumbnails",
      arguments: {
        image_urls: imageUrls,
        page_indices: indices,
      },
    });

    if (destroyed) return;

    if (!result.isError) {
      const thumbnails = parseThumbnailResult(result);
      for (const thumb of thumbnails) {
        thumbnailCache.set(thumb.index, thumb.dataUrl);
        loadedIndices.add(thumb.index);
      }
      // Trigger reactivity
      loadedIndices = new Set(loadedIndices);
    }
  } catch (e) {
    console.error("load-thumbnails failed:", e);
  } finally {
    batchInFlight = false;
    if (destroyed) return;
    // Process queued batch if any
    if (batchQueue.length > 0) {
      const next = batchQueue.splice(0, 8);
      fetchBatch(next);
    }
  }
}

function scheduleBatch() {
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    // Filter out already-requested indices
    const indices = Array.from(pendingIndices).filter(i => !requestedIndices.has(i));
    pendingIndices.clear();

    if (indices.length === 0) return;

    // Mark all as requested
    for (const i of indices) requestedIndices.add(i);

    // Take first 8 for immediate fetch, queue the rest
    const batch = indices.slice(0, 8);
    const rest = indices.slice(8);

    if (rest.length > 0) {
      batchQueue.push(...rest);
    }

    if (batchInFlight) {
      batchQueue.push(...batch);
    } else {
      fetchBatch(batch);
    }
  }, 300);
}

// ---------------------------------------------------------------------------
// IntersectionObserver
// ---------------------------------------------------------------------------

let observer: IntersectionObserver | null = null;

function setupObserver() {
  if (destroyed) return;

  observer = new IntersectionObserver(
    (entries) => {
      let added = false;
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const index = Number((entry.target as HTMLElement).dataset.index);
        if (isNaN(index) || thumbnailCache.has(index) || requestedIndices.has(index)) continue;
        pendingIndices.add(index);
        added = true;
      }
      if (added) scheduleBatch();
    },
    {
      root: containerEl,
      rootMargin: "200px",
    }
  );

  for (const el of placeholderEls) {
    if (el) observer.observe(el);
  }
}

// ---------------------------------------------------------------------------
// Auto-scroll to active thumbnail
// ---------------------------------------------------------------------------

$effect(() => {
  const idx = currentPageIndex;
  if (!containerEl || !placeholderEls[idx]) return;

  const el = placeholderEls[idx];
  const containerRect = containerEl.getBoundingClientRect();
  const elRect = el.getBoundingClientRect();

  if (elRect.top < containerRect.top || elRect.bottom > containerRect.bottom) {
    el.scrollIntoView({ block: "center", behavior: "smooth" });
  }
});

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

onMount(() => {
  requestAnimationFrame(() => setupObserver());
});

onDestroy(() => {
  destroyed = true;
  observer?.disconnect();
  observer = null;
  if (debounceTimer) clearTimeout(debounceTimer);
  batchQueue.length = 0;
  pendingIndices.clear();
});

function getThumbnailUrl(index: number): string | null {
  if (loadedIndices.has(index)) {
    return thumbnailCache.get(index) ?? null;
  }
  return null;
}
</script>

<div class="thumbnail-strip" bind:this={containerEl}>
  {#each Array(totalPages) as _, i}
    <div
      class="thumbnail-slot"
      class:active={i === currentPageIndex}
      data-index={i}
      bind:this={placeholderEls[i]}
    >
      <button
        class="thumbnail-inner"
        onclick={() => onPageSelect(i)}
      >
        {#if getThumbnailUrl(i)}
          <img
            src={getThumbnailUrl(i)}
            alt="Page {i + 1}"
            class="thumbnail-img"
          />
        {:else}
          <div class="thumbnail-placeholder">
            <span class="placeholder-text">{i + 1}</span>
          </div>
        {/if}
      </button>
    </div>
  {/each}
</div>

<style>
.thumbnail-strip {
  width: 120px;
  min-width: 120px;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs, 0.25rem);
  padding: var(--spacing-xs, 0.25rem);
  background: var(--color-background-secondary, light-dark(#f5f4ed, #201d18));
  border-right: 1px solid var(--color-border-primary, light-dark(#d4d2cb, #3a3632));
  border-radius: var(--border-radius-lg, 10px) 0 0 var(--border-radius-lg, 10px);
}

.thumbnail-slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
}

.thumbnail-inner {
  width: 100px;
  min-height: 80px;
  border: 2px solid transparent;
  border-radius: var(--border-radius-md, 6px);
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
  background: var(--color-background-primary, light-dark(#faf9f5, #1a1815));
  padding: 0;
  font: inherit;
  color: inherit;
  text-align: inherit;
  display: block;
}

.thumbnail-slot.active .thumbnail-inner {
  border-color: var(--color-accent, #c15f3c);
  box-shadow: 0 0 0 2px rgba(193, 95, 60, 0.3);
}

.thumbnail-inner:hover {
  border-color: var(--color-accent, #c15f3c);
}

.thumbnail-img {
  width: 100%;
  display: block;
}

.thumbnail-placeholder {
  width: 100%;
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-background-tertiary, light-dark(#ebe9e1, #2a2620));
}

.placeholder-text {
  font-size: var(--font-text-sm-size, 0.875rem);
  color: var(--color-text-secondary, light-dark(#5c5c5c, #a8a6a3));
  opacity: 0.6;
}


</style>
