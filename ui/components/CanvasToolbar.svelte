<script lang="ts">
import { onMount, onDestroy } from "svelte";

const SWATCHES = [
  "#c15f3c", // terracotta
  "#3b82f6", // blue
  "#10b981", // green
  "#f59e0b", // amber
  "#8b5cf6", // purple
  "#ef4444", // red
] as const;

interface Props {
  showTranscription: boolean;
  hasTranscription: boolean;
  canFullscreen: boolean;
  isFullscreen: boolean;
  hasThumbnails: boolean;
  showThumbnails: boolean;
  rightOffset?: number;
  onToggleTranscription: () => void;
  onResetView: () => void;
  onToggleFullscreen: () => void;
  onToggleThumbnails: () => void;
  polygonColor?: string;
  polygonThickness?: number;
  polygonOpacity?: number;
  onPolygonStyleChange?: (key: string, value: string | number) => void;
}

let {
  showTranscription,
  hasTranscription,
  canFullscreen,
  isFullscreen,
  hasThumbnails,
  showThumbnails,
  rightOffset = 0,
  onToggleTranscription,
  onResetView,
  onToggleFullscreen,
  onToggleThumbnails,
  polygonColor = "#c15f3c",
  polygonThickness = 2,
  polygonOpacity = 0.15,
  onPolygonStyleChange,
}: Props = $props();

let showPopover = $state(false);
let popoverBtnEl: HTMLButtonElement;

function onWindowClick(e: MouseEvent) {
  if (!showPopover) return;
  // Close if click is outside the popover and its trigger button
  const target = e.target as Node;
  const popover = popoverBtnEl?.parentElement?.querySelector('.style-popover');
  if (popover && !popover.contains(target) && !popoverBtnEl.contains(target)) {
    showPopover = false;
  }
}

onMount(() => {
  window.addEventListener('click', onWindowClick, true);
});
onDestroy(() => {
  window.removeEventListener('click', onWindowClick, true);
});
</script>

<div class="toolbar" style:right="{rightOffset + 8}px">
  {#if hasTranscription}
    <button
      class="toolbar-btn"
      class:active={showTranscription}
      onclick={onToggleTranscription}
      title={showTranscription ? "Hide transcription" : "Show transcription"}
    >
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M2 4h12M2 8h8M2 12h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      </svg>
    </button>
  {/if}

  {#if hasThumbnails}
    <button
      class="toolbar-btn"
      class:active={showThumbnails}
      onclick={onToggleThumbnails}
      title={showThumbnails ? "Hide pages" : "Show pages"}
    >
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <rect x="1" y="1" width="4" height="5" rx="0.5" stroke="currentColor" stroke-width="1.3"/>
        <rect x="1" y="8.5" width="4" height="5" rx="0.5" stroke="currentColor" stroke-width="1.3"/>
        <path d="M8 3h7M8 7h5M8 11h6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
      </svg>
    </button>
  {/if}

  <button
    class="toolbar-btn"
    onclick={onResetView}
    title="Reset view"
  >
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
      <path d="M1 8a7 7 0 0 1 13-3.5M15 8a7 7 0 0 1-13 3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M14 1v4h-4M2 15v-4h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
  </button>

  <!-- Polygon style settings -->
  <div class="popover-anchor">
    <button
      bind:this={popoverBtnEl}
      class="toolbar-btn"
      class:active={showPopover}
      onclick={() => showPopover = !showPopover}
      title="Overlay style"
    >
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <circle cx="8" cy="8" r="3" stroke="currentColor" stroke-width="1.4"/>
        <circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.2" stroke-dasharray="2 2.5"/>
      </svg>
    </button>

    {#if showPopover}
      <div class="style-popover">
        <div class="popover-section">
          <span class="popover-label">Color</span>
          <div class="swatches">
            {#each SWATCHES as swatch}
              <button
                class="swatch"
                class:selected={polygonColor === swatch}
                style:background={swatch}
                onclick={() => onPolygonStyleChange?.('color', swatch)}
                title={swatch}
              ></button>
            {/each}
          </div>
        </div>
        <div class="popover-section">
          <span class="popover-label">Thickness</span>
          <input
            type="range"
            min="1"
            max="5"
            step="0.5"
            value={polygonThickness}
            oninput={(e) => onPolygonStyleChange?.('thickness', parseFloat((e.target as HTMLInputElement).value))}
          />
        </div>
        <div class="popover-section">
          <span class="popover-label">Opacity</span>
          <input
            type="range"
            min="0.05"
            max="0.5"
            step="0.05"
            value={polygonOpacity}
            oninput={(e) => onPolygonStyleChange?.('opacity', parseFloat((e.target as HTMLInputElement).value))}
          />
        </div>
      </div>
    {/if}
  </div>

  {#if canFullscreen}
    <button
      class="toolbar-btn"
      onclick={onToggleFullscreen}
      title={isFullscreen ? "Exit fullscreen (Esc)" : "Enter fullscreen"}
    >
      {#if isFullscreen}
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path d="M5 1H1v4M15 1h-4M1 15h4M11 15h4v-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M1 1l4.5 4.5M15 1l-4.5 4.5M1 15l4.5-4.5M15 15l-4.5-4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      {:else}
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
          <path d="M1 5V1h4M11 1h4v4M15 11v4h-4M5 15H1v-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M1 1l4.5 4.5M15 1l-4.5 4.5M1 15l4.5-4.5M15 15l-4.5-4.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      {/if}
    </button>
  {/if}
</div>

<style>
.toolbar {
  position: absolute;
  top: 8px;
  z-index: 15;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: right 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  background: var(--color-background-primary, light-dark(#faf9f5, #1a1815));
  color: var(--color-text-secondary, light-dark(#5c5c5c, #a8a6a3));
  cursor: pointer;
  opacity: 0.7;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}

.toolbar-btn:hover {
  opacity: 1;
}

.toolbar-btn.active {
  opacity: 1;
  background: var(--color-accent, #c15f3c);
  color: #fff;
}

/* Popover anchor */
.popover-anchor {
  position: relative;
}

.style-popover {
  position: absolute;
  right: 100%;
  top: 0;
  margin-right: 6px;
  width: 160px;
  padding: 8px;
  background: var(--color-background-primary, light-dark(#faf9f5, #1a1815));
  border-radius: var(--border-radius-md, 6px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18);
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 20;
}

.popover-section {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.popover-label {
  font-size: 0.65rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-tertiary, light-dark(#999, #666));
}

.swatches {
  display: flex;
  gap: 4px;
}

.swatch {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
  padding: 0;
  transition: border-color 0.15s;
}

.swatch:hover {
  border-color: var(--color-text-tertiary, light-dark(#999, #666));
}

.swatch.selected {
  border-color: var(--color-text-primary, light-dark(#1a1815, #faf9f5));
  box-shadow: 0 0 0 1.5px var(--color-background-primary, light-dark(#faf9f5, #1a1815));
}

.style-popover input[type="range"] {
  width: 100%;
  height: 4px;
  accent-color: var(--color-accent, #c15f3c);
  cursor: pointer;
}
</style>
