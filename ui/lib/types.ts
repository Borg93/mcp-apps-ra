/**
 * Type definitions for the Document Viewer
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

export interface PageData {
  index: number;
  imageDataUrl: string;
  alto: PageAltoData;
}

export interface PageUrl {
  image: string;
  alto: string;
}

export interface ThumbnailData {
  index: number;
  dataUrl: string;
}

/** Initial payload from view-document tool */
export interface ViewerData {
  pageUrls: PageUrl[];
  firstPage: PageData;
}

export interface TooltipState {
  text: string;
  x: number;
  y: number;
}
