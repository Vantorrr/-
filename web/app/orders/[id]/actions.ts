"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

const API_URL = process.env.API_URL || "http://127.0.0.1:8000";

async function postJson(path: string, body: unknown): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
}

function refresh(listingId: string) {
  revalidatePath(`/orders/${listingId}`);
  revalidatePath("/");
}

export async function addExpense(listingId: string, formData: FormData) {
  const amount = String(formData.get("amount") || "").trim();
  const currency = String(formData.get("currency") || "").trim();
  const note = String(formData.get("note") || "").trim();
  const spentOn = String(formData.get("spent_on") || "").trim();
  if (!amount || !currency) {
    redirect(`/orders/${listingId}?notice=amount`);
  }
  const response = await postJson(`/api/listings/${listingId}/expenses`, {
    amount,
    currency,
    note,
    spent_on: spentOn || null,
  });
  if (!response.ok) {
    redirect(`/orders/${listingId}?notice=amount`);
  }
  refresh(listingId);
}

export async function setDue(listingId: string, formData: FormData) {
  const due = String(formData.get("due_on") || "").trim();
  const response = await postJson(`/api/listings/${listingId}/due`, { due_on: due || null });
  if (!response.ok) {
    redirect(`/orders/${listingId}?notice=due`);
  }
  refresh(listingId);
}

export async function addTask(listingId: string, formData: FormData) {
  const title = String(formData.get("title") || "").trim();
  const due = String(formData.get("due_at") || "").trim();
  if (!title) {
    redirect(`/orders/${listingId}?notice=task`);
  }
  const response = await postJson(`/api/listings/${listingId}/tasks`, {
    title,
    due_at: due || null,
  });
  if (!response.ok) {
    redirect(`/orders/${listingId}?notice=task`);
  }
  refresh(listingId);
}

export async function toggleTask(listingId: string, taskId: string, formData: FormData) {
  const done = String(formData.get("done") || "") === "true";
  const response = await postJson(`/api/listings/${listingId}/tasks/${taskId}`, { done });
  if (!response.ok) {
    redirect(`/orders/${listingId}?notice=task`);
  }
  refresh(listingId);
}
