import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Narrow — TechJam Shopping Agent",
  description: "See a 50,000-product catalog narrow into the right recommendation.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

