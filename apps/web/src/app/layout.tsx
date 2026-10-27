import type { Metadata } from "next";
import "./globals.css";
import AppChrome from "@/components/AppChrome";

export const metadata: Metadata = {
  title: "Zuzu",
  description: "Zuzu — personal AI assistant",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <AppChrome>{children}</AppChrome>
      </body>
    </html>
  );
}
