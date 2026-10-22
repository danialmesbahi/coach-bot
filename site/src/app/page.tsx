import Image from "next/image";
import CalorieCalculator from "@/components/calorie-calculator";
import HeroLight from "@/components/hero-light";
import MuscleMap from "@/components/muscle-map";
import PathStory from "@/components/path-story";
import PlanPicker from "@/components/plan-picker";
import PulseLine from "@/components/pulse-line";
import Qr from "@/components/qr";
import ServiceShowcase from "@/components/service-showcase";
import finalImg from "@/assets/final-ropes.jpg";
import heroImg from "@/assets/hero-athlete.jpg";
import { getCatalog, type Plan } from "@/lib/catalog";
import { faqs } from "@/lib/faq";
import { journey } from "@/lib/journey";
import { botUrl, config, site } from "@/lib/site";

// Programs come from the panel's catalog, read on every render so panel edits show up at once.
// Host nginx keeps a 60-second copy of the rendered page (deploy/nginx-sensibot-https.conf).
export const dynamic = "force-dynamic";

function jsonLd(plans: Plan[]) {
  const url = site.url;
  return {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Service",
        "@id": `${url}/#service`,
        name: "مربیگری آنلاین و برنامه تمرینی و غذایی اختصاصی سنسی",
        serviceType: "مربیگری آنلاین تناسب اندام",
        provider: { "@id": `${url}/#org` },
        areaServed: { "@type": "Country", name: "Iran" },
        availableChannel: { "@type": "ServiceChannel", serviceUrl: botUrl(), name: "ربات تلگرام سنسی" },
        hasOfferCatalog: {
          "@type": "OfferCatalog",
          name: "برنامه‌های سنسی",
          itemListElement: plans.map((p) => ({
            "@type": "Offer",
            name: p.title,
            description: p.description || p.kindLabel,
            price: p.price * 10,
            priceCurrency: "IRR",
            availability: "https://schema.org/InStock",
            url: p.id ? botUrl(`buy_${p.id}`) : `${url}/#programs`,
          })),
        },
      },
      {
        "@type": "HowTo",
        name: "خرید برنامه اختصاصی از سنسی",
        step: journey.map((s, i) => ({ "@type": "HowToStep", position: i + 1, name: s.title, text: s.body })),
      },
      {
        "@type": "FAQPage",
        mainEntity: faqs.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
      },
    ],
  };
}

export default async function Home() {
  const { plans, salesOpen } = await getCatalog();
  const nutrition = plans.find((p) => p.visual === "nutrition" && p.id);
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd(plans)) }} />

      <section className="hero" aria-labelledby="hero-title">
        <div className="hero__media">
          <Image src={heroImg} alt="ورزشکار در حال ددلیفت با هالتر در نور گرم استودیو" fill preload sizes="100vw" placeholder="blur" className="hero__img" />
        </div>
        <div className="hero__shade" aria-hidden="true" />
        <HeroLight />
        <div className="hero__inner">
          <p className="hero__kicker">{config.hero.kicker}</p>
          <h1 id="hero-title" className="hero__title">
            <span className="hero__strong">{config.hero.title}</span>
            <span className="hero__soft">{config.hero.subtitle}</span>
          </h1>
          <p className="hero__lead">{config.hero.lead}</p>
          <div className="hero__actions">
            <a className="btn btn--ember btn--large" data-magnet href={botUrl("site_hero")} target="_blank" rel="noopener">{config.hero.primaryCta}</a>
            <a className="btn btn--ghost btn--large" href="#programs">{config.hero.secondaryCta}</a>
          </div>
        </div>
        <div className="hero__pulse">
          <PulseLine />
        </div>
      </section>

      <section id="services" className="section section--services" aria-labelledby="svc-title">
        <div className="section__head">
          <h2 id="svc-title">{config.services.title}</h2>
          <p>{config.services.intro}</p>
        </div>
        <ServiceShowcase content={config.services} />
      </section>

      <section id="muscles" className="section section--muscles" aria-labelledby="mm-title">
        <div className="section__head">
          <h2 id="mm-title">{config.muscles.title}</h2>
          <p>{config.muscles.intro}</p>
        </div>
        <MuscleMap content={config.muscles} />
      </section>

      <section id="calories" className="section section--calc" aria-labelledby="calc-title">
        <div className="section__head">
          <h2 id="calc-title">{config.calculator.title}</h2>
          <p>{config.calculator.intro}</p>
        </div>
        <CalorieCalculator content={config.calculator} botHref={botUrl(nutrition?.id ? `buy_${nutrition.id}` : "site_calories")} />
      </section>

      <section id="path" className="section section--path" aria-labelledby="path-title">
        <div className="section__head">
          <h2 id="path-title">{config.journey.title}</h2>
          <p>{config.journey.intro}</p>
        </div>
        <PathStory />
      </section>

      <section id="programs" className="section section--programs" aria-labelledby="programs-title">
        <div className="section__head">
          <h2 id="programs-title">{config.programs.title}</h2>
          <p>{config.programs.intro}</p>
        </div>
        <PlanPicker content={config.programs} plans={plans} botUsername={site.bot.username} salesOpen={salesOpen} />
      </section>

      <section id="faq" className="section" aria-labelledby="faq-title">
        <div className="faq-layout">
          <div className="section__head">
            <h2 id="faq-title">{config.faq.title}</h2>
            <p>{config.faq.intro}</p>
          </div>
          <div className="faq">
            {faqs.map((f) => (
              <details key={f.q} className="faq__item">
                <summary>{f.q}</summary>
                <p>{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section className="final" aria-labelledby="final-title">
        <Image src={finalImg} alt="" fill sizes="100vw" className="final__img" />
        <div className="final__shade" aria-hidden="true" />
        <div className="final__inner">
          <div className="final__copy">
            <h2 id="final-title">{config.final.title}</h2>
            <p>{config.final.text}</p>
            <a className="btn btn--ember btn--large" data-magnet href={botUrl("site_final")} target="_blank" rel="noopener">{config.final.cta}</a>
          </div>
          <div className="final__qr">
            <Qr value={botUrl("site_qr")} label="کد QR ربات تلگرام سنسی" />
            <p>{config.final.qrHint}<span dir="ltr">@{site.bot.username}</span></p>
          </div>
        </div>
      </section>
    </>
  );
}
