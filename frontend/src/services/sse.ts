/** Incremental Server-Sent Events parser for fetch() streams (EventSource can't POST). */
export interface SseEvent {
  event: string;
  data: unknown;
}

export class SseParser {
  private buffer = "";

  feed(chunk: string): SseEvent[] {
    this.buffer += chunk.replace(/\r\n/g, "\n");
    const events: SseEvent[] = [];
    let boundary: number;
    while ((boundary = this.buffer.indexOf("\n\n")) !== -1) {
      const block = this.buffer.slice(0, boundary);
      this.buffer = this.buffer.slice(boundary + 2);
      let event = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
      }
      if (data.length) events.push({ event, data: JSON.parse(data.join("\n")) });
    }
    return events;
  }
}
