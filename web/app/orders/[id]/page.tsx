import Link from "next/link";

import { apiGet, type HistoryEvent, type Listing } from "../../../lib/api";
import { actorLabel, formatWhen, statusLabel } from "../../../lib/labels";
import { addExpense, addTask, setDue, toggleTask } from "./actions";

export const dynamic = "force-dynamic";

const NOTICES: Record<string, string> = {
  amount: "Сумма не сохранена. Нужна сумма больше нуля и валюта из трёх букв.",
  due: "Срок не сохранён. Нужна дата в формате ГГГГ-ММ-ДД или пустое поле, чтобы очистить срок.",
  task: "Задача не сохранена. Нужен текст.",
};

export default async function OrderPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ notice?: string }>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const notice = query.notice ? NOTICES[query.notice] : "";
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
      {notice ? <p className="notice">{notice}</p> : null}
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
              <dt>Срок</dt>
              <dd>{listing.due_on || "неизвестно"}</dd>
              <dt>Расходы</dt>
              <dd>{listing.expenses || "нет"}</dd>
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
          <h2>Срок</h2>
          <form className="stack" action={setDue.bind(null, listing.id)}>
            <label>
              Дата
              <input name="due_on" type="date" />
            </label>
            <button type="submit">Сохранить срок</button>
          </form>
          <form className="inline" action={setDue.bind(null, listing.id)}>
            <button type="submit">Очистить срок</button>
          </form>
          <h2>Расходы</h2>
          {(listing.expense_items || []).length === 0 ? <p className="notice">Расходов нет.</p> : null}
          {(listing.expense_items || []).length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Сумма</th>
                  <th>Валюта</th>
                  <th>Дата</th>
                  <th>Заметка</th>
                </tr>
              </thead>
              <tbody>
                {listing.expense_items?.map((item) => (
                  <tr key={item.id}>
                    <td>{item.amount}</td>
                    <td>{item.currency}</td>
                    <td>{item.spent_on || "дата неизвестна"}</td>
                    <td>{item.note || "без заметки"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          <form className="stack" action={addExpense.bind(null, listing.id)}>
            <label>
              Сумма
              <input name="amount" inputMode="decimal" />
            </label>
            <label>
              Валюта
              <input name="currency" defaultValue="RUB" maxLength={3} />
            </label>
            <label>
              Дата расхода
              <input name="spent_on" type="date" />
            </label>
            <label>
              Заметка
              <input name="note" />
            </label>
            <button type="submit">Добавить расход</button>
          </form>
          <h2>Задачи</h2>
          {(listing.tasks || []).length === 0 ? <p className="notice">Задач нет.</p> : null}
          {(listing.tasks || []).length > 0 ? (
            <table>
              <thead>
                <tr>
                  <th>Задача</th>
                  <th>Срок</th>
                  <th>Состояние</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {listing.tasks?.map((task) => (
                  <tr key={task.id}>
                    <td>{task.title}</td>
                    <td>{task.due_at || "неизвестно"}</td>
                    <td>{task.done ? "сделано" : "открыта"}</td>
                    <td>
                      <form className="inline" action={toggleTask.bind(null, listing.id, task.id)}>
                        <input type="hidden" name="done" value={task.done ? "false" : "true"} />
                        <button type="submit">{task.done ? "Вернуть" : "Готово"}</button>
                      </form>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          <form className="stack" action={addTask.bind(null, listing.id)}>
            <label>
              Текст
              <input name="title" />
            </label>
            <label>
              Срок, UTC
              <input name="due_at" type="datetime-local" />
            </label>
            <button type="submit">Добавить задачу</button>
          </form>
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
