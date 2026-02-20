<script lang="ts">
import type { TextLine } from "../lib/types";

interface Props {
  textLines: TextLine[];
  highlightedLineId: string | null;
  open: boolean;
  width?: number;
  onWidthChange?: (width: number) => void;
  onLineHover: (id: string | null) => void;
  onLineClick: (line: TextLine) => void;
}

let { textLines, highlightedLineId, open, width = 280, onWidthChange, onLineHover, onLineClick }: Props = $props();

let lineEls: HTMLButtonElement[] = [];
let containerEl: HTMLDivElement;
let resizing = $state(false);

// Drag-resize state
let dragStartX = 0;
let dragStartWidth = 0;

function onHandlePointerDown(e: PointerEvent) {
  e.preventDefault();
  resizing = true;
  dragStartX = e.clientX;
  dragStartWidth = width;
  (e.target as HTMLElement).setPointerCapture(e.pointerId);
}

function onHandlePointerMove(e: PointerEvent) {
  if (!resizing) return;
  // Dragging left = increasing width (handle is on left edge)
  const delta = dragStartX - e.clientX;
  const newWidth = Math.max(200, Math.min(500, dragStartWidth + delta));
  onWidthChange?.(newWidth);
}

function onHandlePointerUp(e: PointerEvent) {
  if (!resizing) return;
  resizing = false;
  (e.target as HTMLElement).releasePointerCapture(e.pointerId);
}

// Auto-scroll to highlighted line when changed externally (from canvas hover)
$effect(() => {
  const id = highlightedLineId;
  if (!id || !containerEl || !open) return;
  const idx = textLines.findIndex(l => l.id === id);
  if (idx >= 0 && lineEls[idx]) {
    const el = lineEls[idx];
    const containerRect = containerEl.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    if (elRect.top < containerRect.top || elRect.bottom > containerRect.bottom) {
      el.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }
});
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="panel" class:open class:resizing style:width="{width}px">
  <div
    class="resize-handle"
    onpointerdown={onHandlePointerDown}
    onpointermove={onHandlePointerMove}
    onpointerup={onHandlePointerUp}
  ></div>
  <div class="panel-lines" bind:this={containerEl}>
    {#each textLines as line, i}
      <button
        class="line-item"
        class:highlighted={line.id === highlightedLineId}
        bind:this={lineEls[i]}
        onpointerenter={() => onLineHover(line.id)}
        onpointerleave={() => onLineHover(null)}
        onclick={() => onLineClick(line)}
      >
        {line.transcription}
      </button>
    {/each}
    {#if textLines.length === 0}
      <div class="no-lines">No transcribed text on this page</div>
    {/if}
  </div>
</div>

<style>
.panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-background-primary, light-dark(#faf9f5, #1a1815));
  border-left: 1px solid var(--color-border-primary, light-dark(#d4d2cb, #3a3632));
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.06);
  z-index: 10;
  transform: translateX(100%);
  pointer-events: none;
  transition: transform 0.2s ease;
  font-family: inherit;
}

.panel.resizing {
  transition: none;
}

.panel.open {
  transform: translateX(0);
  pointer-events: auto;
}

.resize-handle {
  position: absolute;
  top: 0;
  left: -3px;
  bottom: 0;
  width: 6px;
  cursor: col-resize;
  z-index: 11;
}

.resize-handle::after {
  content: "";
  position: absolute;
  top: 0;
  left: 2px;
  bottom: 0;
  width: 2px;
  border-radius: 1px;
  background: transparent;
  transition: background 0.15s;
}

.resize-handle:hover::after,
.panel.resizing .resize-handle::after {
  background: var(--color-accent, #c15f3c);
  opacity: 0.4;
}

.panel-lines {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-xs, 0.25rem) 0 var(--spacing-xs, 0.25rem) var(--spacing-sm, 0.5rem);
}

.line-item {
  display: block;
  width: 100%;
  padding: var(--spacing-xs, 0.25rem) var(--spacing-sm, 0.5rem);
  font: inherit;
  font-size: var(--font-text-sm-size, 0.875rem);
  line-height: 1.5;
  text-align: left;
  color: var(--color-text-primary, light-dark(#2c2c2c, #e8e6e3));
  background: none;
  border: none;
  border-left: 2px solid transparent;
  cursor: pointer;
  transition: background 0.1s, border-color 0.1s;
}

.line-item:hover,
.line-item.highlighted {
  background: var(--claude-selection, rgba(193, 95, 60, 0.19));
  border-left-color: var(--color-accent, #c15f3c);
}

.no-lines {
  padding: var(--spacing-lg, 1.5rem) var(--spacing-md, 1rem);
  color: var(--color-text-secondary, light-dark(#5c5c5c, #a8a6a3));
  font-size: var(--font-text-sm-size, 0.875rem);
  font-style: italic;
  text-align: center;
}
</style>
