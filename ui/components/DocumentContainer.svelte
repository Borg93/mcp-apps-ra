<script lang="ts">
import type { App } from "@modelcontextprotocol/ext-apps";
import type { ViewerData, PageData } from "../lib/types";
import { parsePageResult } from "../lib/utils";
import DocumentViewer from "./DocumentViewer.svelte";
import ThumbnailStrip from "./ThumbnailStrip.svelte";

interface Props {
  app: App;
  data: ViewerData;
  canFullscreen: boolean;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
}

let { app, data, canFullscreen, isFullscreen, onToggleFullscreen }: Props = $props();

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let currentPageIndex = $state(0);
let totalPages = $derived(data.pageUrls.length);
let hasThumbnails = $derived(data.pageUrls.length > 1);
let showThumbnails = $state(true);
let currentPageMetadata = $derived(data.pageMetadata[currentPageIndex] ?? "");

// Client-side page cache (seeded lazily in the page-index effect below)
let pageCache = new Map<number, PageData>();
let currentPage = $state<PageData | null>(null);

function handlePageSelect(index: number) {
  currentPageIndex = index;
}

// ---------------------------------------------------------------------------
// Page fetching + caching
// ---------------------------------------------------------------------------

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

/** Fetch and set current page — use cache or fetch ALTO via callServerTool */
async function fetchAndRenderPage(index: number) {
  if (index < 0 || index >= totalPages) return;

  // Check cache first — instant render, no server call
  const cached = pageCache.get(index);
  if (cached) {
    currentPage = cached;
    prefetchAdjacentPages(index);
    return;
  }

  const page = await fetchPageData(index);
  if (page && currentPageIndex === index) {
    currentPage = page;
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
// Watch page index changes
// ---------------------------------------------------------------------------

let lastRenderedIndex = -1;
$effect(() => {
  const idx = currentPageIndex;
  if (idx !== lastRenderedIndex) {
    lastRenderedIndex = idx;
    fetchAndRenderPage(idx);
  }
});
</script>

<div class="split-layout">
  {#if hasThumbnails}
    <div class="thumbnail-wrapper" class:collapsed={!showThumbnails}>
      <ThumbnailStrip
        {app}
        {data}
        {currentPageIndex}
        onPageSelect={handlePageSelect}
      />
    </div>
  {/if}
  {#if currentPage}
    <DocumentViewer
      {app}
      pageData={currentPage}
      pageIndex={currentPageIndex}
      {totalPages}
      pageMetadata={currentPageMetadata}
      onPageChange={handlePageSelect}
      {canFullscreen}
      {isFullscreen}
      {onToggleFullscreen}
      {hasThumbnails}
      {showThumbnails}
      onToggleThumbnails={() => showThumbnails = !showThumbnails}
    />
  {:else}
    <div class="page-loading">
      <div class="page-loading-shimmer"></div>
    </div>
  {/if}
</div>

<style>
.split-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  max-height: 100%;
  overflow: hidden;
  gap: 0;
}

.thumbnail-wrapper {
  width: 120px;
  min-width: 120px;
  overflow: hidden;
  transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.thumbnail-wrapper.collapsed {
  width: 0;
  min-width: 0;
}

.page-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-background-secondary, light-dark(#f5f4ed, #201d18));
}

.page-loading-shimmer {
  width: 60%;
  height: 80%;
  border-radius: var(--border-radius-md, 6px);
  background: linear-gradient(90deg, var(--color-background-tertiary, light-dark(#ebe9e1, #2a2620)) 25%, var(--color-background-secondary, light-dark(#f5f4ed, #201d18)) 50%, var(--color-background-tertiary, light-dark(#ebe9e1, #2a2620)) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
</style>
