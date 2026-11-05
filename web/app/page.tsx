import Link from "next/link";

import { apiGet, type Listing, type StatusFunnel } from "../lib/api";
import { STATUS_OPTIONS, statusLabel } from "../lib/labels";

export const dynamic = "force-dynamic";

type Search = {
  status?: string;
  source?: string;
  min_score?: string;
};

function cleanSource(value: string | undefined): string {
  const source = (value || "").trim();
  return /^[A-Za-z0-9_-]{1,64}$/.test(source) ? source : "";
}

function cleanScore(value: string | undefined): string {
  const score = (value || "").trim();
  return /^\d{1,3}$/.test(score) ? score : "";
}

function cleanStatus(value: string | undefined): string {
  const status = (value || "").trim();
  return STATUS_OPTIONS.some(([code]) => code === status) ? status : "";
}

export default async function HomePage({ searchParams }: { searchParams: Promise<Search> }) {
  const queryState = await searchParams;
  const status = cleanStatus(queryState.status);
  const source = cleanSource(queryState.source);
  const minScore = cleanScore(queryState.min_score);
  const query = new URLSearchParams();
  if (status) query.set("status", status);
  if (source) query.set("source_id", source);
  if (minScore) query.set("min_score", minScore);
  query.set("limit", "100");

  const exportQuery = new URLSearchParams(query);
  let rows: Listing[] = [];
  let funnel: StatusFunnel | null = null;
  let error = "";
  let funnelError = "";
  try {
    rows = await apiGet<Listing[]>(`/api/listings?${query.toString()}`);
  } catch {
    error = "Не удалось получить заказы из API.";
  }
  try {
    funnel = await apiGet<StatusFunnel>("/api/stats/statuses");
  } catch {
    funnelError = "Счётчики недоступны.";
  }

  return (
    <>
      <h1>Заказы</h1>
      <p className="muted">Фильтр по статусу, источнику и баллу. Отправка заявок отсюда не запускается.</p>
      <h2>Конверсия по статусам</h2>
      {funnelError ? <p className="notice">{funnelError}</p> : null}
      {funnel ? (
        <div className="counts">
          {STATUS_OPTIONS.map(([code, label]) => (
            <div className="count" key={code}>
              <strong>{label}</strong>
              <div>сейчас {funnel.current[code] ?? 0}</div>
              <div>дошли {funnel.reached[code] ?? 0}</div>
            </div>
          ))}
        </div>
      ) : null}
      <form method="get">
        <label>
          Статус
          <select name="status" defaultValue={status}>
            <option value="">все</option>
            {STATUS_OPTIONS.map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Источник
          <input name="source" defaultValue={source} placeholder="fl_ru" />
        </label>
        <label>
          Балл от
          <input name="min_score" type="number" min={0} max={100} defaultValue={minScore} />
        </label>
        <button type="submit">Показать</button>
        <a href={`/export?${exportQuery.toString()}`}>Скачать CSV</a>
      </form>
      {error ? <p className="notice">{error}</p> : null}
      {!error && rows.length === 0 ? <p className="notice">Заказов нет.</p> : null}
      {rows.length > 0 ? (
        <table>
          <thead>
            <tr>
              <th>Название</th>
              <th>Источник</th>
              <th>Статус</th>
              <th>Балл</th>
              <th>Бюджет</th>
              <th>Срок</th>
              <th>Расходы</th>
              <th>В CRM</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>
                  <Link href={`/orders/${row.id}`}>{row.title}</Link>
                </td>
                <td>{row.source_id}</td>
                <td>{statusLabel(row.status)}</td>
                <td>{row.score}</td>
                <td>{row.budget}</td>
                <td>{row.due_on || "неизвестно"}</td>
                <td>{row.expenses || "нет"}</td>
                <td>{row.in_crm ? "да" : "нет"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
    </>
  );
}
