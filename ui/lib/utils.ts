/**
 * Utility functions for the Riksarkivet Document Viewer
 */

import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { ViewerData } from "./types";

/**
 * Parse tool result into ViewerData.
 * Tries structuredContent first (PDF pattern), falls back to content text.
 */
export function parseToolResult(result: CallToolResult): ViewerData | null {
  // Try structuredContent first (matches PDF server pattern)
  const sc = (result as any).structuredContent;
  if (sc && typeof sc === "object" && "imageUrls" in sc) {
    return sc as ViewerData;
  }

  // Fallback: parse from content text
  const textContent = result.content?.find((c) => c.type === "text");
  if (textContent && "text" in textContent) {
    try {
      return JSON.parse(textContent.text) as ViewerData;
    } catch (e) {
      console.error("[parseToolResult] JSON.parse failed:", e);
      return null;
    }
  }

  return null;
}

/**
 * Truncate text with ellipsis
 */
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
}
