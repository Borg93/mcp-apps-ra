/**
 * Utility functions for the Document Viewer
 */

import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { ViewerData, PageData, ThumbnailData } from "./types";

/**
 * Parse initial tool result (view-document) into ViewerData.
 */
export function parseToolResult(result: CallToolResult): ViewerData | null {
  const sc = (result as any).structuredContent;
  if (sc && typeof sc === "object" && "pageUrls" in sc && "firstPage" in sc) {
    return sc as ViewerData;
  }
  return null;
}

/**
 * Parse load-page tool result into a single PageData.
 */
export function parsePageResult(result: CallToolResult): PageData | null {
  const sc = (result as any).structuredContent;
  if (sc && typeof sc === "object" && "page" in sc) {
    return sc.page as PageData;
  }
  return null;
}

/**
 * Parse load-thumbnails tool result into ThumbnailData array.
 */
export function parseThumbnailResult(result: CallToolResult): ThumbnailData[] {
  const sc = (result as any).structuredContent;
  if (sc && typeof sc === "object" && "thumbnails" in sc) {
    return sc.thumbnails as ThumbnailData[];
  }
  return [];
}
