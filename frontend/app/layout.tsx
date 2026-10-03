export const metadata = {
  title: "آفاق — AFAQ",
  description: "منصة استكشاف معرفي مصدرها موثّق حول آيات القرآن الكريم",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ar" dir="rtl">
      <head>
        {/* KFGQPC Hafs font: the Quran text is encoded for it (e.g. the ۝ ayah-end sign).
            The .ttf is not in git; copy it to public/fonts/ (see README). Falls back if absent. */}
        <style>{`@font-face { font-family: "KFGQPC Hafs"; src: url("/fonts/kfgqpc_hafs_v30.ttf") format("truetype"); font-display: swap; }`}</style>
      </head>
      <body style={{ fontFamily: "Tahoma, Arial, sans-serif", margin: 0 }}>
        {children}
      </body>
    </html>
  );
}
