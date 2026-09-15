export interface SseEvent {
  event: string;
  data: unknown;
}

export interface SseParser {
  push(text: string): void;
}

// A block ends at a blank line. Splitting the whole accumulated buffer (rather than each chunk)
// is what makes a CRLF pair straddling two chunks harmless: the lone "\r" simply stays buffered.
const BLOCK_SEPARATOR = /\r\n\r\n|\n\n|\r\r/;
const LINE_SEPARATOR = /\r\n|\n|\r/;

function parseBlock(block: string): SseEvent | undefined {
  let name = "message";
  const data: string[] = [];

  for (const line of block.split(LINE_SEPARATOR)) {
    if (line === "" || line.startsWith(":")) continue;
    const colon = line.indexOf(":");
    const field = colon === -1 ? line : line.slice(0, colon);
    const rawValue = colon === -1 ? "" : line.slice(colon + 1);
    const value = rawValue.startsWith(" ") ? rawValue.slice(1) : rawValue;
    if (field === "event") name = value;
    if (field === "data") data.push(value);
  }

  // An event carrying no data line is not dispatched, per the SSE specification.
  if (data.length === 0) return undefined;
  return { event: name, data: JSON.parse(data.join("\n")) };
}

export function createSseParser(onEvent: (event: SseEvent) => void): SseParser {
  let buffer = "";

  return {
    push(text: string): void {
      buffer += text;
      const blocks = buffer.split(BLOCK_SEPARATOR);
      buffer = blocks.pop() ?? "";
      for (const block of blocks) {
        const event = parseBlock(block);
        if (event) onEvent(event);
      }
    },
  };
}
