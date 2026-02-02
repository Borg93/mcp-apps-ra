<script lang="ts">
import { onMount } from "svelte";
import {
  App,
  applyDocumentTheme,
  applyHostFonts,
  applyHostStyleVariables,
  type McpUiHostContext,
} from "@modelcontextprotocol/ext-apps";

// Components
import UploadView from "./components/UploadView.svelte";
import DocumentViewer from "./components/DocumentViewer.svelte";
import EmptyState from "./components/EmptyState.svelte";

// Types & Utils
import type { DocumentData } from "./lib/types";
import { parseDocumentResult } from "./lib/utils";

// =============================================================================
// State
// =============================================================================

let app = $state<App | null>(null);
let hostContext = $state<McpUiHostContext | undefined>();
let documentData = $state<DocumentData | null>(null);
let uploadMode = $state(false);

// =============================================================================
// Effects
// =============================================================================

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

// =============================================================================
// Lifecycle
// =============================================================================

onMount(async () => {
  const instance = new App({ name: "Riksarkivet Viewer", version: "1.0.0" });

  instance.ontoolinput = (params) => {
    console.info("Received tool call input:", params);
  };

  instance.ontoolresult = (result) => {
    console.info("Received tool call result:", result);
    const data = parseDocumentResult(result);
    if (data) {
      if (data.mode === "upload") {
        uploadMode = true;
        documentData = null;
      } else if (!data.error) {
        documentData = data;
        uploadMode = false;
      }
    }
  };

  instance.ontoolcancelled = (params) => {
    console.info("Tool call cancelled:", params.reason);
  };

  instance.onerror = (err) => {
    console.error("App error:", err);
  };

  instance.onhostcontextchanged = (params) => {
    hostContext = { ...hostContext, ...params };
  };

  await instance.connect();
  app = instance;
  hostContext = instance.getHostContext();
});

// =============================================================================
// Handlers
// =============================================================================

function handleDocumentLoaded(data: DocumentData) {
  documentData = data;
  uploadMode = false;
}

function handleReset() {
  documentData = null;
  uploadMode = true;
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

  {:else if uploadMode}
    <UploadView onDocumentLoaded={handleDocumentLoaded} />

  {:else if documentData && !documentData.error}
    <DocumentViewer {app} {documentData} onReset={handleReset} />

  {:else if documentData?.error}
    <div class="error-state">
      <h2>Error Loading Document</h2>
      <p>{documentData.message}</p>
      <p class="image-id">{documentData.imageId}</p>
    </div>

  {:else}
    <EmptyState />
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

.error-state {
  text-align: center;
  padding: var(--spacing-lg, 2rem);
  background: var(--color-background-secondary);
  border-radius: var(--border-radius-lg, 10px);
  border: 1px solid var(--color-border-primary);
}

.error-state h2 {
  margin: 0 0 var(--spacing-sm, 0.5rem) 0;
  font-size: var(--font-heading-lg-size, 1.25rem);
  color: var(--color-error);
}

.error-state p {
  margin: var(--spacing-sm, 0.5rem) 0;
  color: var(--color-text-secondary);
}

.image-id {
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
}
</style>
