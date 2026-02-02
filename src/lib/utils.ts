/**
 * Utility functions for the Riksarkivet Document Viewer
 */

import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";
import type { DocumentData } from "./types";

/**
 * Parse tool result from MCP server into DocumentData
 */
export function parseDocumentResult(result: CallToolResult): DocumentData | null {
  const textContent = result.content?.find((c) => c.type === "text");
  if (textContent && "text" in textContent) {
    try {
      return JSON.parse(textContent.text) as DocumentData;
    } catch {
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

/**
 * Extract filename without extension
 */
export function getFilenameWithoutExtension(filename: string): string {
  return filename.replace(/\.[^/.]+$/, "");
}
