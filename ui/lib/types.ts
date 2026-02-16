/**
 * Type definitions for the Riksarkivet Document Viewer
 */

export interface TextLine {
  id: string;
  polygon: string;
  transcription: string;
  hpos: number;
  vpos: number;
  width: number;
  height: number;
}

export interface PageData {
  pageNumber: number;
  imageService?: Record<string, unknown> | null;
  imageUrl?: string | null;
  pageWidth: number;
  pageHeight: number;
  textLines: TextLine[];
  label: string;
}

export interface ManifestData {
  manifestUrl: string;
  title: string;
  totalPages: number;
  pages: PageData[];
}

export interface DocumentData {
  totalPages: number;
  pages: PageData[];
  error?: boolean;
  message?: string;
}

export interface TooltipState {
  text: string;
  x: number;
  y: number;
}

/** Union type for tool results - both tools return pages */
export type ViewerData = ManifestData | DocumentData;
