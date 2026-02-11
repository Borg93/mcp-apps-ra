<script lang="ts">
import { z } from "zod";
import type { DocumentData } from "../lib/types";
import { parseAltoXml, readFileAsDataUrl } from "../lib/alto-parser";
import { getFilenameWithoutExtension, truncateText } from "../lib/utils";

// Props
interface Props {
  onDocumentLoaded: (data: DocumentData) => void;
}

let { onDocumentLoaded }: Props = $props();

// Zod validation schema
const uploadSchema = z.object({
  altoFile: z.custom<File>(
    (val) => val instanceof File && val.name.toLowerCase().endsWith(".xml"),
    { message: "ALTO file must be an XML file" }
  ),
  imageFile: z.custom<File>(
    (val) => val instanceof File && /\.(jpg|jpeg|png|tiff?|gif|webp)$/i.test(val.name),
    { message: "Image must be a valid image file (jpg, png, tiff, gif, webp)" }
  ),
});

// State
let altoFile = $state<File | null>(null);
let imageFile = $state<File | null>(null);
let loading = $state(false);
let error = $state("");

// Handlers
function handleAltoFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files?.[0]) {
    altoFile = input.files[0];
    error = "";
  }
}

function handleImageFileChange(e: Event) {
  const input = e.target as HTMLInputElement;
  if (input.files?.[0]) {
    imageFile = input.files[0];
    error = "";
  }
}

async function handleUpload() {
  // Validate with Zod
  const validation = uploadSchema.safeParse({ altoFile, imageFile });
  if (!validation.success) {
    error = validation.error.issues[0].message;
    return;
  }

  loading = true;
  error = "";

  try {
    // Parse ALTO XML
    const altoText = await validation.data.altoFile.text();
    const altoData = parseAltoXml(altoText);

    // Read image as data URL
    const imageDataUrl = await readFileAsDataUrl(validation.data.imageFile);

    // Create document data and notify parent
    const documentData: DocumentData = {
      imageId: getFilenameWithoutExtension(validation.data.altoFile.name),
      imageUrl: imageDataUrl,
      altoUrl: `local://${validation.data.altoFile.name}`,
      pageWidth: altoData.pageWidth,
      pageHeight: altoData.pageHeight,
      textLines: altoData.textLines,
      totalLines: altoData.textLines.length,
      fullText: truncateText(altoData.fullText, 800),
    };

    onDocumentLoaded(documentData);
  } catch (e) {
    console.error(e);
    error = e instanceof Error ? e.message : "Failed to process files";
  } finally {
    loading = false;
  }
}
</script>

<div class="upload-state">
  <h2>Upload Document</h2>
  <p>Select an ALTO XML file and corresponding image to view the document with text overlays.</p>

  <div class="upload-controls">
    <div class="upload-field">
      <label for="alto-input">ALTO XML File</label>
      <input
        id="alto-input"
        type="file"
        accept=".xml,application/xml,text/xml"
        onchange={handleAltoFileChange}
      />
      {#if altoFile}
        <span class="file-name">{altoFile.name}</span>
      {/if}
    </div>

    <div class="upload-field">
      <label for="image-input">Image File</label>
      <input
        id="image-input"
        type="file"
        accept=".jpg,.jpeg,.png,.tiff,.tif,image/*"
        onchange={handleImageFileChange}
      />
      {#if imageFile}
        <span class="file-name">{imageFile.name}</span>
      {/if}
    </div>

    {#if error}
      <p class="upload-error">{error}</p>
    {/if}

    <button
      class="control-btn primary"
      onclick={handleUpload}
      disabled={loading || !altoFile || !imageFile}
    >
      {loading ? "Processing..." : "Load Document"}
    </button>
  </div>
</div>

<style>
.upload-state {
  text-align: center;
  padding: var(--spacing-md, 1rem);
  background: var(--color-background-secondary);
  border-radius: var(--border-radius-lg, 10px);
  border: 1px solid var(--color-border-primary);
  max-width: 400px;
  width: 100%;
}

.upload-state h2 {
  margin: 0 0 var(--spacing-xs, 0.25rem) 0;
  font-size: var(--font-heading-md-size, 1.125rem);
}

.upload-state p {
  margin: 0 0 var(--spacing-sm, 0.5rem) 0;
  color: var(--color-text-secondary);
  font-size: var(--font-text-sm-size, 0.875rem);
}

.upload-controls {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm, 0.5rem);
  max-width: 320px;
  margin: 0 auto;
  text-align: left;
}

.upload-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.upload-field label {
  font-weight: var(--font-weight-medium, 500);
  font-size: var(--font-text-sm-size, 0.875rem);
  color: var(--color-text-primary);
}

.upload-field input[type="file"] {
  padding: var(--spacing-xs, 0.25rem);
  background: var(--color-background-primary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--border-radius-md, 6px);
  color: var(--color-text-primary);
  cursor: pointer;
  font-size: var(--font-text-xs-size, 0.75rem);
}

.upload-field input[type="file"]::file-selector-button {
  padding: 2px var(--spacing-xs, 0.25rem);
  margin-right: var(--spacing-xs, 0.25rem);
  background: var(--color-accent);
  border: none;
  border-radius: var(--border-radius-sm, 4px);
  color: var(--color-text-on-accent);
  cursor: pointer;
  font-size: var(--font-text-xs-size, 0.75rem);
}

.file-name {
  font-size: var(--font-text-xs-size, 0.75rem);
  color: var(--color-text-secondary);
}

.upload-error {
  color: var(--color-error);
  font-size: var(--font-text-xs-size, 0.75rem);
  margin: 0;
}

.control-btn {
  padding: var(--spacing-xs, 0.25rem) var(--spacing-sm, 0.5rem);
  background: var(--color-background-secondary);
  border: 1px solid var(--color-border-primary);
  border-radius: var(--border-radius-md, 6px);
  color: var(--color-text-primary);
  cursor: pointer;
  font-size: var(--font-text-sm-size, 0.875rem);
  transition: all 0.2s ease;
}

.control-btn.primary {
  background: var(--color-accent);
  border-color: var(--color-accent);
  color: var(--color-text-on-accent);
  width: auto;
  margin-top: var(--spacing-xs, 0.25rem);
}

.control-btn.primary:hover {
  background: var(--color-accent-dark);
  border-color: var(--color-accent-dark);
}

.control-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
