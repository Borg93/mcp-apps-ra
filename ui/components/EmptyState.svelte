<script lang="ts">
// No props needed - just a static display component
</script>

<div class="empty-state">
  <h2>Riksarkivet Document Viewer</h2>
  <p>Waiting for document data...</p>
  <p class="hint">
    Use <code>view-manifest</code> with a IIIF manifest URL
    <br />
    for multi-page documents with page navigation.
    <br /><br />
    Or use <code>view-document</code> with image and ALTO URLs
    <br />
    for individual pages.
  </p>
</div>

<style>
.empty-state {
  text-align: center;
  padding: var(--spacing-lg, 2rem);
  background: var(--color-background-secondary);
  border-radius: var(--border-radius-lg, 10px);
  border: 1px solid var(--color-border-primary);
  max-width: 400px;
  width: 100%;
}

.empty-state h2 {
  margin: 0 0 var(--spacing-sm, 0.5rem) 0;
  font-size: var(--font-heading-lg-size, 1.25rem);
}

.empty-state p {
  margin: var(--spacing-sm, 0.5rem) 0;
  color: var(--color-text-secondary);
}

.empty-state code {
  background: var(--color-background-tertiary);
  padding: 0.125rem 0.5rem;
  border-radius: var(--border-radius-sm, 4px);
  font-family: var(--font-mono);
  color: var(--color-accent);
}
</style>
