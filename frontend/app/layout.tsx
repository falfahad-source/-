import "./globals.css";

export const metadata = {
  title: "آفاق — AFAQ",
  description: "منصة استكشاف معرفي مصدرها موثّق حول آيات القرآن الكريم",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font */}
        <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600&family=Noto+Naskh+Arabic:wght@400;600&family=Reem+Kufi:wght@500;700&display=swap" />
      </head>
      <body>{children}</body>
    </html>
  );
}
