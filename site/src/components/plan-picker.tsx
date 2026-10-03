import type { Plan } from "@/lib/catalog";
import { toman } from "@/lib/format";
import type config from "../../sensi.config";

/**
 * Programs straight from the panel's catalog, as compact product cards that fit one screen:
 * a grid on desktop, a swipeable row on phones. Each card buys its own product in the bot.
 */
export default function PlanPicker({ plans, botUsername, salesOpen, content }: { plans: Plan[]; botUsername: string; salesOpen: boolean; content: (typeof config)["programs"] }) {
  if (!plans.length) return null;

  return (
    <div className={`plans${plans.length === 1 ? " is-single" : ""}`}>
      {plans.map((plan, i) => {
        const href = `https://t.me/${botUsername}?start=${plan.id ? `buy_${plan.id}` : "site_programs"}`;
        return (
          <article key={`${plan.id ?? plan.title}-${i}`} className={`plan${plan.featured ? " is-featured" : ""}`} data-spot>
            <div className="plan__main">
              <div className="plan__top">
                <span className="plan__kind">{plan.kindLabel}</span>
                {plan.featured && plans.length > 1 && <span className="plan__flag">{content.featuredLabel}</span>}
              </div>
              <h3 className="plan__name">{plan.title}</h3>
              {plan.description && <p className="plan__desc">{plan.description}</p>}
              <ul className="plan__gets" aria-label={content.getsTitle}>
                {content.gets[plan.kind].map((x) => <li key={x}>{x}</li>)}
              </ul>
              {plan.sends.length > 0 && (
                <p className="plan__sends">
                  <span>{content.sendsTitle}:</span> {plan.sends.join("، ")}
                </p>
              )}
            </div>
            <div className="plan__side">
              <p className="plan__price">
                <b>{toman(plan.price)}</b>
                <span>تومان</span>
                {plan.duration && <em>{plan.duration}</em>}
              </p>
              {salesOpen ? (
                <a className="btn btn--ember plan__cta" href={href} target="_blank" rel="noopener">
                  {content.buyLabel.replace("{title}", plan.title)}
                </a>
              ) : (
                <p className="plan__closed">{content.closedText}</p>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}
