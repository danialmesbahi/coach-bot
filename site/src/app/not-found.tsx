import Link from "next/link";

export default function NotFound() {
  return (
    <section className="doc not-found">
      <p className="not-found__code">۴۰۴</p>
      <h1>این صفحه پیدا نشد.</h1>
      <p className="doc__lead">نشانی را بررسی کن یا به صفحه اصلی برگرد.</p>
      <Link className="btn btn--ember btn--large" href="/">رفتن به صفحه اصلی</Link>
    </section>
  );
}
