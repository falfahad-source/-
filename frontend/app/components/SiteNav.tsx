import { link } from "./links";

export type Section = "home" | "search" | "history" | "quran" | "ai";

// short: the label in the phone's bottom tab bar, where the full one does not fit
const ITEMS: { key: Section; label: string; short: string; icon: string; href: () => string }[] = [
  { key: "home", label: "الرئيسية", short: "الرئيسية", icon: "⌂", href: link.home },
  { key: "search", label: "بحث جديد", short: "بحث", icon: "⌕", href: () => link.search() },
  { key: "history", label: "سجل البحث", short: "السجل", icon: "↺", href: link.history },
  { key: "quran", label: "القرآن الكريم", short: "القرآن", icon: "۞", href: () => link.quran() },
  { key: "ai", label: "الذكاء الاصطناعي في الإعجاز العلمي", short: "الإعجاز", icon: "✦", href: () => link.ai() },
];

export default function SiteNav({ current }: { current: Section }) {
  return (
    <nav className="sitenav" aria-label="أقسام المنصة">
      {/* the home page shows the name large in its own header */}
      {current !== "home" && <a className="brand" href={link.home()}>آفاق</a>}
      <div className="sitenav-links">
        {ITEMS.map((i) => (
          <a key={i.key} href={i.href()} aria-current={i.key === current ? "page" : undefined} className={i.key === "home" ? "tab-home" : undefined}>
            <span className="tab-icon" aria-hidden="true">{i.icon}</span>
            <span className="tab-full">{i.label}</span>
            <span className="tab-short" aria-hidden="true">{i.short}</span>
          </a>
        ))}
      </div>
    </nav>
  );
}
