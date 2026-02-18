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

export interface PageAltoData {
  textLines: TextLine[];
  pageWidth: number;
  pageHeight: number;
}

export interface ImageChunk {
  bytes: string;
  offset: number;
  byteCount: number;
  totalBytes: number;
  hasMore: boolean;
}

export interface ViewerData {
  imageUrls: string[];
  altoUrls: string[];
  error?: boolean;
  message?: string;
}

export interface TooltipState {
  text: string;
  x: number;
  y: number;
}
