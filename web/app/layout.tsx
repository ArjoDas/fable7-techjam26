import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Fable7 · From prompt to results",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml", sizes: "any", media: "(prefers-color-scheme: light)" },
      { url: "/icon-dark.svg", type: "image/svg+xml", sizes: "any", media: "(prefers-color-scheme: dark)" },
    ],
  },
  description:
    "An animated walkthrough of how the Fable7 conversational shopping agent turns a query into ranked recommendations.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link
          rel="preconnect"
          href="https://fonts.gstatic.com"
          crossOrigin="anonymous"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:ital,wght@0,400;0,500;0,600;1,400;1,500;1,600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
