export const metadata = {
  title: "آفاق — AFAQ",
  description: "منصة استكشاف معرفي مصدرها موثّق حول آيات القرآن الكريم",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <body style={{ fontFamily: "Tahoma, Arial, sans-serif", margin: 0 }}>
        {children}
      </body>
    </html>
  );
}
