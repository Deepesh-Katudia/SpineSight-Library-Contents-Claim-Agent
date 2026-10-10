// Mirrors services/api/app/schema/claim_packet.py (subset the UI reads).

export interface PriceQuote {
  amount: number | null;
  currency: string;
  source: string;
  url: string;
  retrieved_at: string;
  converted: boolean;
  original_amount: number | null;
  original_currency: string;
  fx_rate: number | null;
  condition_assumed: string;
}

export interface ItemPrice {
  low: number | null;
  high: number | null;
  currency: string;
  source: string;
  url: string;
  retrieved_at: string;
  converted: boolean;
}

export type BookStatus = "identified" | "unidentified" | "needs_appraisal";

export interface Book {
  id: string;
  shelf: string;
  position: number;
  frame_ref: string;
  status: BookStatus;
  title: string;
  author: string;
  edition: string;
  isbn: string;
  spine_text_raw: string;
  spine_height_cm: number | null;
  spine_thickness_cm: number | null;
  id_confidence: number;
  replacement_cost: PriceQuote;
  used_value: PriceQuote;
  appraisal_reason: string;
  unidentified_reason: string;
  excluded: boolean;
}

export interface Item {
  id: string;
  category: string;
  description: string;
  brand_model: string;
  frame_ref: string;
  dimensions_cm: { w: number | null; h: number | null; d: number | null };
  status: "priced" | "range" | "needs_appraisal" | "unpriced";
  replacement_cost: ItemPrice;
  confidence: number;
}

export interface Room {
  length_m: number | null;
  width_m: number | null;
  height_m: number | null;
  floor_area_m2: number | null;
  wall_area_m2: number | null;
  shelved_wall_area_m2: number | null;
  floor_area_ft2: number | null;
  wall_area_ft2: number | null;
  shape: string;
  scale_method: string;
  confidence: number;
}

export interface Totals {
  book_count: number;
  books_identified: number;
  books_unidentified: number;
  books_needs_appraisal: number;
  shelf_run_m: number;
  books_replacement_cost: number;
  books_used_value: number;
  items_replacement_cost_low: number;
  items_replacement_cost_high: number;
  excluded_from_totals: number;
  currency: string;
}

export interface ClaimPacket {
  sweep: { id: string; captured_at: string; device: string; duration_s: number; country: string; currency: string };
  room: Room;
  books: Book[];
  items: Item[];
  totals: Totals;
  review_queue: { ref_id: string; reason: string }[];
  metrics: { stage: string; latency_s: number; calls: number; cost_usd: number }[];
}

export interface PacketSummary {
  sweep_id: string;
  currency: string;
  book_count: number;
  books_identified: number;
  books_unidentified: number;
  books_needs_appraisal: number;
  shelf_run_m: number;
  books_replacement_cost: number;
  books_used_value: number;
  items: number;
  items_low: number;
  items_high: number;
  floor_area_m2: number | null;
  wall_area_m2: number | null;
  review_queue: number;
  time_to_packet_s: number | null;
}

// ---- live events (SSE) ----
export interface LiveBook {
  id: string;
  shelf: string;
  text: string;
  title: string;
  author: string;
  legibility: number;
  height_cm: number | null;
  thickness_cm: number | null;
  frame_ref: string;
}

export interface LiveItem {
  id: string;
  category: string;
  description: string;
  brand_model: string;
  frame_ref: string;
}

export interface LiveWall {
  label: string;
  width_m: number;
  height_m: number;
  method: string;
}

export interface LiveTokenResponse {
  token: string;
}
