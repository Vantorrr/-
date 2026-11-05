export const STATUS_LABELS: Record<string, string> = {
  found: "найдено",
  checked: "проверено",
  proposal_ready: "черновик готов",
  awaiting_approval: "ждёт подтверждения",
  sent: "отправлено",
  replied: "есть ответ",
  negotiation: "переговоры",
  contract: "договор",
  won: "выиграно",
  lost: "проиграно",
  rejected: "отклонено",
};

export const STATUS_OPTIONS = Object.entries(STATUS_LABELS);

export function statusLabel(status: string | null | undefined): string {
  if (!status) return "неизвестно";
  return STATUS_LABELS[status] ?? status;
}

export function actorLabel(actor: string | null | undefined): string {
  if (actor === "system") return "система";
  if (actor === "operator") return "оператор";
  return actor || "неизвестно";
}

export function formatWhen(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "неизвестно";
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date);
}
