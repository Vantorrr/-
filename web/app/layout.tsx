import type { ReactNode } from "react";

import "./globals.css";

export const metadata = {
  title: "Заказы — Qora Group",
  description: "Список заявок",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
