import "./fonts.css";
import "./globals.css";

export const metadata = {
  title: "آفاق — AFAQ",
  description: "منصة استكشاف معرفي مصدرها موثّق حول آيات القرآن الكريم",
};

export const viewport = { themeColor: "#12302F" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <body>{children}</body>
    </html>
  );
}
