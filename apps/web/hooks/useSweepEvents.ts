"use client";

import { useEffect, useReducer } from "react";

import { api } from "@/lib/api";
import type { LiveBook, LiveItem, LiveWall, PacketSummary } from "@/lib/types";

export interface Hint {
  key: string;
  text: string;
  at: number;
}

export interface InventoryState {
  books: Record<string, LiveBook>;
  items: Record<string, LiveItem>;
  walls: Record<string, LiveWall>;
  identified: Record<string, { status: string; title: string; author: string }>;
  frames: number;
  frameErrors: number;
  target: string;
  lastHint: Hint | null;
  packet: PacketSummary | null;
}

export const initialInventory: InventoryState = {
  books: {},
  items: {},
  walls: {},
  identified: {},
  frames: 0,
  frameErrors: 0,
  target: "",
  lastHint: null,
  packet: null,
};

type Action = { type: string; data: Record<string, unknown> };

function reducer(state: InventoryState, { type, data }: Action): InventoryState {
  switch (type) {
    case "book":
      return { ...state, books: { ...state.books, [String(data.id)]: data as unknown as LiveBook } };
    case "item":
      return { ...state, items: { ...state.items, [String(data.id)]: data as unknown as LiveItem } };
    case "wall":
      return { ...state, walls: { ...state.walls, [String(data.label)]: data as unknown as LiveWall } };
    case "identified": {
      const key = (data.key as string[]).join("|");
      return {
        ...state,
        identified: {
          ...state.identified,
          [key]: { status: String(data.status), title: String(data.title ?? ""), author: String(data.author ?? "") },
        },
      };
    }
    case "frame":
      return { ...state, frames: state.frames + 1 };
    case "frame_error":
      return { ...state, frameErrors: state.frameErrors + 1 };
    case "target":
      return { ...state, target: String(data.target) };
    case "hint":
      return { ...state, lastHint: { key: String(data.key), text: String(data.text), at: Date.now() } };
    case "packet_ready":
      return { ...state, packet: data as unknown as PacketSummary };
    default:
      return state;
  }
}

const EVENT_TYPES = ["book", "item", "wall", "identified", "frame", "frame_error", "target", "hint", "packet_ready"];

/** Subscribes to the sweep's SSE stream and folds events into an inventory snapshot. */
export function useSweepEvents(sweepId: string | null, onHint?: (hint: Hint) => void): InventoryState {
  const [state, dispatch] = useReducer(reducer, initialInventory);

  useEffect(() => {
    if (!sweepId) return;
    const source = new EventSource(api.eventsUrl(sweepId));
    const listeners = EVENT_TYPES.map((type) => {
      const fn = (e: MessageEvent<string>) => {
        const data = JSON.parse(e.data) as Record<string, unknown>;
        dispatch({ type, data });
        if (type === "hint" && onHint) onHint({ key: String(data.key), text: String(data.text), at: Date.now() });
      };
      source.addEventListener(type, fn);
      return [type, fn] as const;
    });
    return () => {
      listeners.forEach(([type, fn]) => source.removeEventListener(type, fn));
      source.close();
    };
  }, [sweepId, onHint]);

  return state;
}

export function identifiedFor(state: InventoryState, book: LiveBook) {
  if (!book.title) return undefined;
  const prefix = `${book.title.toLowerCase()}|${book.author.toLowerCase()}|`;
  const key = Object.keys(state.identified).find((k) => k.startsWith(prefix));
  return key ? state.identified[key] : undefined;
}
