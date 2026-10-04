import { link } from "./links";

export type Section = "home" | "search" | "history" | "quran" | "ai";

const ITEMS: { key: Section; label: string; href: () => string }[] = [
  { key: "home", label: "الرئيسية", href: link.home },
  { key: "search", label: "بحث جديد", href: () => link.search() },
  { key: "history", label: "سجل البحث", href: link.history },
  { key: "quran", label: "القرآن الكريم", href: () => link.quran() },
  { key: "ai", label: "الذكاء الاصطناعي في الإعجاز العلمي", href: () => link.ai() },
];

export default function SiteNav({ current }: { current: Section }) {
  return (
    <nav className="sitenav" aria-label="أقسام المنصة">
      <a className="brand" href={link.home()}>آفاق</a>
      <div className="sitenav-links">
        {ITEMS.slice(1).map((i) => (
          <a key={i.key} href={i.href()} aria-current={i.key === current ? "page" : undefined}>{i.label}</a>
        ))}
      </div>
    </nav>
  );
}
