/**
 * Utility functions for the Riksarkivet Document Viewer
 */

import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { ViewerData } from "./types";

/**
 * Parse tool result from MCP server into ViewerData.
 * Handles both manifest and document result shapes.
 */
export function parseToolResult(result: CallToolResult): ViewerData | null {
  const textContent = result.content?.find((c) => c.type === "text");
  if (textContent && "text" in textContent) {
    try {
      return JSON.parse(textContent.text) as ViewerData;
    } catch {
      return null;
    }
  }
  return null;
}

/**
 * Check if a ViewerData result is a manifest (has manifestUrl).
 */
export function isManifestData(
  data: ViewerData,
): data is import("./types").ManifestData {
  return "manifestUrl" in data;
}

/**
 * Truncate text with ellipsis
 */
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
}
