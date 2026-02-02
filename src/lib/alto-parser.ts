/**
 * Client-side ALTO XML parser
 * Extracts text lines, polygons, and page dimensions from ALTO XML format
 */

import type { TextLine, AltoData } from "./types";

/**
 * Parse ALTO XML string and extract document structure
 */
export function parseAltoXml(xmlString: string): AltoData {
  const textLines: TextLine[] = [];
  const transcriptionLines: string[] = [];

  // Extract page dimensions from <Page> element
  const pageMatch = xmlString.match(/<Page[^>]*WIDTH="(\d+)"[^>]*HEIGHT="(\d+)"/);
  const pageWidth = pageMatch ? parseInt(pageMatch[1]) : 6192;
  const pageHeight = pageMatch ? parseInt(pageMatch[2]) : 5432;

  // Extract all TextLine elements with their attributes
  const textLineRegex = /<TextLine[^>]*ID="([^"]*)"[^>]*HPOS="(\d+)"[^>]*VPOS="(\d+)"[^>]*HEIGHT="(\d+)"[^>]*WIDTH="(\d+)"[^>]*>([\s\S]*?)<\/TextLine>/g;

  let match;
  while ((match = textLineRegex.exec(xmlString)) !== null) {
    const lineId = match[1];
    const hpos = parseInt(match[2]);
    const vpos = parseInt(match[3]);
    const height = parseInt(match[4]);
    const width = parseInt(match[5]);
    const lineContent = match[6];

    // Extract polygon points for overlay rendering
    const polygonMatch = lineContent.match(/<Polygon[^>]*POINTS="([^"]*)"/);
    const polygon = polygonMatch ? polygonMatch[1] : "";

    // Extract all String elements (words) and join them
    const words: string[] = [];
    const stringRegex = /<String[^>]*CONTENT="([^"]*)"/g;
    let wordMatch;
    while ((wordMatch = stringRegex.exec(lineContent)) !== null) {
      words.push(wordMatch[1]);
    }
    const transcription = words.join(" ");

    // Only include lines that have both polygon and transcription
    if (polygon && transcription) {
      textLines.push({
        id: lineId,
        polygon,
        transcription,
        hpos,
        vpos,
        width,
        height,
      });
      transcriptionLines.push(transcription);
    }
  }

  return {
    textLines,
    pageWidth,
    pageHeight,
    fullText: transcriptionLines.join("\n"),
  };
}

/**
 * Read a file as text
 */
export async function readFileAsText(file: File): Promise<string> {
  return file.text();
}

/**
 * Read a file as data URL (for images)
 */
export async function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}
