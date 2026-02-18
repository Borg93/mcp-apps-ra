<script lang="ts">
import { onMount } from "svelte";
import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";

import DocumentViewer from "./components/DocumentViewer.svelte";
import ThumbnailStrip from "./components/ThumbnailStrip.svelte";
import EmptyState from "./components/EmptyState.svelte";

import type { ViewerData } from "./lib/types";
import { parseToolResult } from "./lib/utils";

const DEFAULT_INLINE_HEIGHT = 300;

let app = $state<App | null>(null);
let hostContext = $state<McpUiHostContext | undefined>();
let viewerData = $state<ViewerData | null>(null);
let error = $state<string | null>(null);
let isStreaming = $state(false);
let streamingMessage = $state("");

let currentPageIndex = $state(0);
let hasData = $derived(viewerData && viewerData.pageUrls.length > 0);
let showThumbnails = $derived(viewerData && viewerData.pageUrls.length > 1);
let isCardState = $derived(!hasData || !!error || !app);

function handlePageSelect(index: number) {
  currentPageIndex = index;
}

$effect(() => {
  if (hostContext?.theme) applyDocumentTheme(hostContext.theme);
  if (hostContext?.styles?.variables) applyHostStyleVariables(hostContext.styles.variables);
  if (hostContext?.styles?.css?.fonts) applyHostFonts(hostContext.styles.css.fonts);
});

$effect(() => {
  if (!app) return;
  const height = (isCardState && !isStreaming) ? DEFAULT_INLINE_HEIGHT : 700;
  setTimeout(() => app?.sendSizeChanged({ height }), 50);
});

onMount(async () => {
  const instance = new App(
    { name: "Document Viewer", version: "1.0.0" },
    { availableDisplayModes: ["inline"] },
    { autoResize: false },
  );

  instance.ontoolinputpartial = (params) => {
    // Show skeleton while the LLM is still streaming the tool call
    if (!viewerData) {
      isStreaming = true;
    }
  };

  instance.ontoolinput = (params) => {
    console.info("Tool input:", params);
    isStreaming = true;
    // Show what's being loaded based on tool arguments
    const args = params.arguments as Record<string, unknown>;
    const pageCount = (args?.image_urls as string[])?.length;
    streamingMessage = pageCount
      ? `Loading ${pageCount} page document...`
      : "Loading document...";
  };

  instance.ontoolresult = (result) => {
    console.info("Tool result:", result);
    if (result.isError) {
      error = result.content?.map((c: any) => ("text" in c ? c.text : "")).join(" ") ?? "Unknown error";
      return;
    }
    const data = parseToolResult(result);
    if (data) {
      currentPageIndex = 0;
      viewerData = data;
      error = null;
    } else {
      error = "Failed to parse tool result";
    }
  };

  instance.ontoolcancelled = (params) => {
    error = `Cancelled: ${params.reason}`;
  };

  instance.onerror = (err) => {
    console.error("App error:", err);
    error = err.message;
  };

  instance.onhostcontextchanged = (params) => {
    hostContext = { ...hostContext, ...params };
  };

  await instance.connect();
  app = instance;
  hostContext = instance.getHostContext();
});
</script>

<main
  class="main"
  class:card-state={isCardState}
  style:padding-top={hostContext?.safeAreaInsets?.top ? `${hostContext.safeAreaInsets.top}px` : undefined}
  style:padding-right={hostContext?.safeAreaInsets?.right ? `${hostContext.safeAreaInsets.right}px` : undefined}
  style:padding-bottom={hostContext?.safeAreaInsets?.bottom ? `${hostContext.safeAreaInsets.bottom}px` : undefined}
  style:padding-left={hostContext?.safeAreaInsets?.left ? `${hostContext.safeAreaInsets.left}px` : undefined}
>
  {#if !app}
    <div class="loading">Connecting...</div>
  {:else if isStreaming && !viewerData}
    <div class="skeleton">
      <div class="skeleton-strip">
        {#each Array(4) as _}
          <div class="skeleton-thumb"></div>
        {/each}
      </div>
      <div class="skeleton-viewer">
        <div class="skeleton-shimmer"></div>
        {#if streamingMessage}
          <span class="skeleton-message">{streamingMessage}</span>
        {/if}
      </div>
    </div>
  {:else if viewerData && hasData && !error}
    <div class="split-layout">
      {#if showThumbnails}
        <ThumbnailStrip
          {app}
          data={viewerData}
          {currentPageIndex}
          onPageSelect={handlePageSelect}
        />
      {/if}
      <DocumentViewer
        {app}
        data={viewerData}
        {currentPageIndex}
        onPageChange={handlePageSelect}
      />
    </div>
  {:else if error}
    <div class="error-state">
      <h2>Error</h2>
      <p>{error}</p>
    </div>
  {:else}
    <EmptyState />
  {/if}
</main>

<style>
.main {
  width: 100%;
  min-height: 100%;
  padding: var(--spacing-sm, 0.5rem);
  display: flex;
  flex-direction: column;
  background: var(--color-background-primary);
  border-radius: var(--border-radius-lg, 10px);
  border: 1px solid var(--color-border-primary);
  overflow: hidden;
}

.main.card-state {
  justify-content: center;
  align-items: center;
}

.split-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  gap: 0;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  font-size: 1rem;
  color: var(--color-text-secondary);
}

.skeleton {
  display: flex;
  flex: 1;
  gap: 0;
  min-height: 400px;
}
.skeleton-strip {
  width: 120px;
  min-width: 120px;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs, 0.25rem);
  padding: var(--spacing-xs, 0.25rem);
  background: var(--color-background-secondary, #f5f5f5);
  border-right: 1px solid var(--color-border-primary);
  border-radius: var(--border-radius-lg, 10px) 0 0 var(--border-radius-lg, 10px);
}
.skeleton-thumb {
  width: 100px;
  height: 120px;
  border-radius: var(--border-radius-md, 6px);
  background: linear-gradient(90deg, var(--color-background-tertiary, #eee) 25%, var(--color-background-secondary, #f5f5f5) 50%, var(--color-background-tertiary, #eee) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  margin: 0 auto;
}
.skeleton-viewer {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-md, 0.75rem);
  background: var(--color-background-secondary, #f5f5f5);
  border-radius: 0 var(--border-radius-lg, 10px) var(--border-radius-lg, 10px) 0;
}
.skeleton-message {
  font-size: var(--font-text-sm-size, 0.875rem);
  color: var(--color-text-secondary);
}
.skeleton-shimmer {
  width: 60%;
  height: 80%;
  border-radius: var(--border-radius-md, 6px);
  background: linear-gradient(90deg, var(--color-background-tertiary, #eee) 25%, var(--color-background-secondary, #f5f5f5) 50%, var(--color-background-tertiary, #eee) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.error-state {
  text-align: center;
  padding: var(--spacing-lg, 1.5rem);
  background: var(--color-background-secondary);
  border-radius: var(--border-radius-lg, 10px);
  border: 1px solid var(--color-border-primary);
}

.error-state h2 {
  margin: 0 0 var(--spacing-sm, 0.5rem) 0;
  font-size: 1.25rem;
  color: var(--color-error);
}

.error-state p {
  margin: var(--spacing-sm, 0.5rem) 0;
  color: var(--color-text-secondary);
}
</style>
