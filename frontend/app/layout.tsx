import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/theme";
import { SiteHeader } from "@/components/site-header";
import { PwaRegister } from "@/components/pwa";

export const metadata: Metadata = {
  title: { default: "SnapFix", template: "%s · SnapFix" },
  description: "Snap a photo, say one sentence: AI turns it into a routed, de-duplicated, prioritized work order.",
  manifest: "/manifest.json",
  appleWebApp: { capable: true, title: "SnapFix", statusBarStyle: "default" },
  icons: { icon: "/icons/icon-192.png", apple: "/icons/icon-192.png" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#0f766e" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1220" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2"
        >
          Skip to content
        </a>
        <ThemeProvider>
          <SiteHeader />
          <main id="main">{children}</main>
          <PwaRegister />
        </ThemeProvider>
      </body>
    </html>
  );
}
