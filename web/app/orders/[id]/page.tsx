import Link from "next/link";

import { apiGet, type HistoryEvent, type Listing } from "../../../lib/api";
import { actorLabel, formatWhen, statusLabel } from "../../../lib/labels";

export const dynamic = "force-dynamic";

export default async function OrderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let listing: Listing | null = null;
  let history: HistoryEvent[] = [];
  let missing = false;
  let error = "";
  try {
    listing = await apiGet<Listing>(`/api/listings/${id}`);
  } catch (caught) {
    const status = (caught as { status?: number }).status;
    if (status === 404) missing = true;
    else error = "Не удалось получить заказ из API.";
  }
  if (listing) {
    try {
      history = await apiGet<HistoryEvent[]>(`/api/listings/${id}/history`);
    } catch {
      error = "Не удалось получить историю статусов.";
    }
  }

  return (
    <>
      <p>
        <Link href="/">К списку</Link>
      </p>
      {missing ? <p className="notice">Заказ не найден.</p> : null}
      {error ? <p className="notice">{error}</p> : null}
      {listing ? (
        <>
          <h1>{listing.title}</h1>
          <div className="card">
            <dl>
              <dt>Статус</dt>
              <dd>{statusLabel(listing.status)}</dd>
              <dt>Источник</dt>
              <dd>{listing.source_id}</dd>
              <dt>Балл</dt>
              <dd>{listing.score}</dd>
              <dt>Бюджет</dt>
              <dd>{listing.budget}</dd>
              <dt>Предлагаемая цена</dt>
              <dd>{listing.proposed_price || "неизвестно"}</dd>
              <dt>Заказчик</dt>
              <dd>
                {listing.buyer_name} ({listing.buyer_type})
              </dd>
              <dt>В CRM</dt>
              <dd>{listing.in_crm ? "да" : "нет"}</dd>
              <dt>Ссылка</dt>
              <dd>
                <a href={listing.url}>{listing.url}</a>
              </dd>
              <dt>Текст объявления</dt>
              <dd className="draft">{listing.description || "неизвестно"}</dd>
              <dt>Черновик</dt>
              <dd className="draft">
                {listing.proposal_origin_label ? `(${listing.proposal_origin_label}) ` : ""}
                {listing.proposal || "неизвестно"}
              </dd>
            </dl>
          </div>
          <h2>История статусов</h2>
          {history.length === 0 ? <p className="notice">Истории статусов нет.</p> : null}
          {history.length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Когда</th>
                  <th>Было</th>
                  <th>Стало</th>
                  <th>Кто</th>
                  <th>Заметка</th>
                </tr>
              </thead>
              <tbody>
                {history.map((event, index) => (
                  <tr key={`${event.at}-${index}`}>
                    <td>{formatWhen(event.at)}</td>
                    <td>{event.from_status ? statusLabel(event.from_status) : "—"}</td>
                    <td>{statusLabel(event.to_status)}</td>
                    <td>{actorLabel(event.actor)}</td>
                    <td>{event.note || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
        </>
      ) : null}
    </>
  );
}
