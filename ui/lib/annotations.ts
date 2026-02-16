/**
 * Convert ALTO TextLine data to Annotorious ImageAnnotation format.
 */

import type { TextLine } from "./types";

/**
 * Parse ALTO polygon string "x1,y1 x2,y2 ..." into [x,y] tuples.
 */
function parsePolygonPoints(polygon: string): [number, number][] {
  return polygon
    .trim()
    .split(/\s+/)
    .map((pair) => {
      const [x, y] = pair.split(",").map(Number);
      return [x, y] as [number, number];
    });
}

/**
 * Compute bounding box from a list of [x,y] points.
 */
function computeBounds(points: [number, number][]) {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  for (const [x, y] of points) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }
  return { minX, minY, maxX, maxY };
}

/**
 * Convert a single ALTO TextLine to an Annotorious ImageAnnotation.
 */
export function altoLineToAnnotation(line: TextLine) {
  const points = parsePolygonPoints(line.polygon);
  const bounds = computeBounds(points);

  return {
    id: line.id,
    bodies: [
      {
        id: `body-${line.id}`,
        annotation: line.id,
        type: "TextualBody",
        value: line.transcription,
        purpose: "commenting" as const,
      },
    ],
    target: {
      annotation: line.id,
      selector: {
        type: "POLYGON" as const,
        geometry: {
          points,
          bounds,
        },
      },
    },
  };
}

/**
 * Convert all text lines for a page to Annotorious annotations.
 */
export function textLinesToAnnotations(textLines: TextLine[]) {
  return textLines.map(altoLineToAnnotation);
}
