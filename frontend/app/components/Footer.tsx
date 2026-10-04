import { DEMO } from "./links";

/** The same footer on every page: where the mushaf text comes from, and what AFAQ uses AI for. */
export default function Footer({ review = false }: { review?: boolean }) {
  return (
    <footer className="foot">
      نص المصحف: مجمع الملك فهد لطباعة المصحف الشريف (رواية حفص، الإصدار 3.0).
      <br />
      آفاق لا يطلب من الذكاء الاصطناعي تفسير القرآن، بل يستعمله للتنقل في المعرفة الموثقة حوله.
      {review && !DEMO && <><br /><a href="/review">مراجعة المقارنات (للباحثين)</a></>}
    </footer>
  );
}
