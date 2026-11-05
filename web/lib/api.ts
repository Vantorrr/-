export type ExpenseItem = {
  id: string;
  amount: string;
  currency: string;
  note: string;
  spent_on: string | null;
};

export type TaskItem = {
  id: string;
  title: string;
  due_at: string | null;
  done: boolean;
};

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
  commercial_proposal?: string | null;
  proposal_threshold?: number;
  proposal_origin: string;
  proposal_origin_label: string;
  proposed_price: string;
  in_crm: boolean;
  due_on: string;
  expenses?: string;
  expense_items?: ExpenseItem[];
  tasks?: TaskItem[];
  description?: string;
};

export type StatusFunnel = {
  current: Record<string, number>;
  reached: Record<string, number>;
  labels: Record<string, string>;
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
