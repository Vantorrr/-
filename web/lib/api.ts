export type Listing = {
  id: string;
  title: string;
  source_id: string;
  status: string | null;
  score: number;
  budget: string;
  url: string;
  buyer_name: string;
  buyer_type: string;
  proposal: string | null;
  proposal_origin: string;
  proposal_origin_label: string;
  proposed_price: string;
  in_crm: boolean;
  description?: string;
};

export type HistoryEvent = {
  from_status: string | null;
  to_status: string;
  actor: string;
  note: string | null;
  at: string;
};

const API_URL = process.env.API_URL || "http://127.0.0.1:8000";

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    const error = new Error(`api ${response.status}`) as Error & { status: number };
    error.status = response.status;
    throw error;
  }
  return response.json() as Promise<T>;
}
