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

export interface AltoData {
  textLines: TextLine[];
  pageWidth: number;
  pageHeight: number;
  fullText: string;
}

export interface DocumentData {
  imageId: string;
  imageUrl: string;
  altoUrl: string;
  pageWidth: number;
  pageHeight: number;
  textLines: TextLine[];
  totalLines: number;
  fullText: string;
  error?: boolean;
  message?: string;
  mode?: string;
}

export interface TooltipState {
  text: string;
  x: number;
  y: number;
}
