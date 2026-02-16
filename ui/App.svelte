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
import DocumentViewer from "./components/DocumentViewer.svelte";
import EmptyState from "./components/EmptyState.svelte";

// Types & Utils
import type { ViewerData } from "./lib/types";
import { parseToolResult } from "./lib/utils";

// =============================================================================
// Constants
// =============================================================================

const DEFAULT_INLINE_HEIGHT = 300;

// =============================================================================
// State
// =============================================================================

let app = $state<App | null>(null);
let hostContext = $state<McpUiHostContext | undefined>();
let viewerData = $state<ViewerData | null>(null);
let displayMode = $state<"inline" | "fullscreen">("inline");

// Derived: whether we're showing a "card" state (empty/error) vs viewer
let hasError = $derived(viewerData && "error" in viewerData && viewerData.error);
let hasPages = $derived(viewerData && "pages" in viewerData && viewerData.pages?.length > 0);
let isCardState = $derived(!hasPages || hasError || !app);

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
  if (hostContext?.displayMode) {
    displayMode = hostContext.displayMode as "inline" | "fullscreen";
  }
});

// Request size for non-viewer states
$effect(() => {
  if (app && isCardState && displayMode !== "fullscreen") {
    setTimeout(() => {
      app?.sendSizeChanged({ height: DEFAULT_INLINE_HEIGHT });
    }, 50);
  }
});

// =============================================================================
// Lifecycle
// =============================================================================

onMount(async () => {
  const instance = new App(
    { name: "Riksarkivet Viewer", version: "1.0.0" },
    {},
    { autoResize: false }
  );

  instance.ontoolinput = (params) => {
    console.info("Received tool call input:", params);
  };

  instance.ontoolresult = (result) => {
    console.info("Received tool call result:", result);
    const data = parseToolResult(result);
    if (data && !("error" in data && data.error)) {
      viewerData = data;
    } else if (data) {
      viewerData = data;
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
</script>

<main
  class="main"
  class:fullscreen={displayMode === "fullscreen"}
  class:card-state={isCardState}
  style:padding-top={hostContext?.safeAreaInsets?.top ? `${hostContext.safeAreaInsets.top}px` : undefined}
  style:padding-right={hostContext?.safeAreaInsets?.right ? `${hostContext.safeAreaInsets.right}px` : undefined}
  style:padding-bottom={hostContext?.safeAreaInsets?.bottom ? `${hostContext.safeAreaInsets.bottom}px` : undefined}
  style:padding-left={hostContext?.safeAreaInsets?.left ? `${hostContext.safeAreaInsets.left}px` : undefined}
>
  {#if !app}
    <div class="loading">Connecting...</div>

  {:else if viewerData && hasPages && !hasError}
    <DocumentViewer {app} data={viewerData} {displayMode} />

  {:else if hasError && viewerData}
    <div class="error-state">
      <h2>Error Loading Document</h2>
      <p>{"message" in viewerData ? viewerData.message : "Unknown error"}</p>
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

/* Center card states (empty, error, loading) */
.main.card-state {
  justify-content: center;
  align-items: center;
}

.main.fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  border-radius: 0;
  border: none;
  overflow: hidden;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  font-size: 1rem;
  color: var(--color-text-secondary);
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
