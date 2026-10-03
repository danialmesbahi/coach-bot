import Image from "next/image";
import back from "@/assets/anatomy-back.jpg";
import front from "@/assets/anatomy.jpg";
import type { ChatItem, JourneyStep } from "@/lib/journey";

const fa = (s: string) => s.replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[Number(d)]);

function Lines({ text }: { text: string }) {
  return (
    <>
      {text.split("\n").map((line, i) => (
        <span key={i} className="tg-line">{line}</span>
      ))}
    </>
  );
}

function Meta({ time, out }: { time: string; out?: boolean }) {
  return (
    <span className="tg-meta">
      {time}
      {out && (
        <svg viewBox="0 0 18 10" aria-hidden="true"><path d="M1 5.5l3 3L10.5 1M7 8.5l1 .5L16.5 1" /></svg>
      )}
    </span>
  );
}

/** Builds a playback timeline: bot messages are preceded by a typing indicator. */
function timeline(items: ChatItem[]) {
  let t = 0.35;
  return items.map((item) => {
    const bot = item.kind === "bot" || item.kind === "file";
    const typing = bot ? t : null;
    const at = bot ? t + 0.95 : t;
    t = at + (bot ? 0.55 : 0.75);
    return { typing, at };
  });
}


type Time = { typing: number | null; at: number };

export function renderItem(item: ChatItem, key: string, slot: Time, minute: number, still: boolean) {
          const { typing, at } = slot;
          const time = fa(`12:${String(minute).padStart(2, "0")}`);
          const style = { ["--d" as string]: `${at}s` };
          const cls = still ? " is-static" : "";
          const parts = [];
          if (typing !== null && !still)
            parts.push(
              <div key={`${key}-t`} className="tg-typing" style={{ ["--d" as string]: `${typing}s` }}>
                <i /><i /><i />
              </div>,
            );
          if (item.kind === "user")
            parts.push(
              <div key={key} className={`tg-msg tg-msg--out${cls}`} style={style}>
                <div className="tg-bubble"><Lines text={item.text} /><Meta time={time} out /></div>
              </div>,
            );
          else if (item.kind === "photos")
            parts.push(
              <div key={key} className={`tg-msg tg-msg--out${cls}`} style={style}>
                <div className="tg-bubble tg-bubble--album">
                  {Array.from({ length: item.count }, (_, k) => (
                    <span key={k} className="tg-photo">
                      <Image src={k % 2 ? back : front} alt="" fill sizes="90px" style={{ transform: k > 1 ? "scaleX(-1)" : undefined }} />
                    </span>
                  ))}
                  <Meta time={time} out />
                </div>
              </div>,
            );
          else if (item.kind === "file")
            parts.push(
              <div key={key} className={`tg-msg tg-msg--in${cls}`} style={style}>
                <div className="tg-bubble tg-bubble--file">
                  <span className="tg-file__icon"><svg viewBox="0 0 24 24"><path d="M12 5v10M7.5 11l4.5 4.5 4.5-4.5M6 19h12" /></svg></span>
                  <span className="tg-file__name"><b>{item.name}</b><small>{item.size}</small></span>
                  <Meta time={time} />
                </div>
              </div>,
            );
          else
            parts.push(
              <div key={key} className={`tg-msg tg-msg--in${cls}`} style={style}>
                <div className="tg-bubble"><Lines text={item.text} /><Meta time={time} /></div>
                {item.buttons && (
                  <div className="tg-inline">
                    {item.buttons.map((row, r) => (
                      <div key={r} className="tg-inline__row">{row.map((b) => <span key={b}>{b}</span>)}</div>
                    ))}
                  </div>
                )}
              </div>,
            );
          return parts;
}

/**
 * A dark-mode Telegram conversation mirroring the real bot. `steps` is the conversation so far:
 * earlier steps stay on screen (like a real chat history) and only the last step animates in,
 * so changing steps never empties the phone.
 */
export default function PhoneChat({ steps, compact = false }: { steps: JourneyStep[]; compact?: boolean }) {
  // an empty conversation renders the idle phone (before the section is on screen)
  const step: JourneyStep = steps[steps.length - 1] ?? { id: "idle", title: "", body: "", chat: [] };
  const times = timeline(step.chat);
  const first = steps.length === 1 ? times[0]?.typing ?? times[0]?.at ?? 0 : null;
  const pressedAt = (() => {
    const i = step.chat.findIndex((c) => c.kind === "user" && c.text === step.pressed);
    return i >= 0 ? times[i].at - 0.25 : 0.6;
  })();
  return (
    <div className={`tg${compact ? " tg--compact" : ""}`} aria-hidden="true">
      <div className="tg__island" />
      <div className="tg__status">
        <span dir="ltr">9:41</span>
        <span className="tg__icons">
          <svg viewBox="0 0 18 12"><path d="M1 11h2V8H1zM5 11h2V6H5zM9 11h2V4H9zM13 11h2V1h-2z" /></svg>
          <svg viewBox="0 0 16 12"><path d="M8 11.5l2.2-2.6a3.4 3.4 0 0 0-4.4 0zM3.4 6.6l1.5 1.7a4.8 4.8 0 0 1 6.2 0l1.5-1.7a7.1 7.1 0 0 0-9.2 0zM1 3.8l1.5 1.7a8.4 8.4 0 0 1 11 0L15 3.8a10.7 10.7 0 0 0-14 0z" /></svg>
          <span className="tg__battery"><i /></span>
        </span>
      </div>
      <div className="tg__head">
        <span className="tg__back">
          <svg viewBox="0 0 12 20"><path d="M10 2L2 10l8 8" /></svg>
          <b>۳</b>
        </span>
        <span className="tg__title">
          <b>سنسی</b>
          <small>ربات</small>
        </span>
        <span className="tg__avatar" />
      </div>
      <div className="tg__chat">
        {steps.length > 0 && <span className={`tg-date${first === null ? " is-static" : ""}`} style={first === null ? undefined : { ["--d" as string]: `${first}s` }}>امروز</span>}
        {steps.slice(0, -1).map((past, p) => past.chat.map((item, i) => renderItem(item, `${past.id}-${i}`, timeline(past.chat)[i], 2 + p * 3 + i, true)))}
        {step.chat.map((item, i) => renderItem(item, `${step.id}-${i}`, times[i], 2 + (steps.length - 1) * 3 + i, false))}
      </div>
      <div className="tg__composer">
        <span className="tg__menu">
          <svg viewBox="0 0 16 16"><path d="M3 4h10M3 8h10M3 12h10" /></svg>
          منو
        </span>
        <span className="tg__input">پیام</span>
        <svg className="tg__icon" viewBox="0 0 24 24"><rect x="4" y="7" width="16" height="11" rx="2" /><path d="M7 10h1M10 10h1M13 10h1M16 10h1M8 14h8" /></svg>
        <svg className="tg__icon" viewBox="0 0 24 24"><rect x="9" y="3" width="6" height="11" rx="3" /><path d="M6 11a6 6 0 0 0 12 0M12 17v3" /></svg>
      </div>
      {step.keyboard && (
        <div className="tg__kb">
          {step.keyboard.map((row, r) => (
            <div key={r} className="tg__kb-row">
              {row.map((b) => (
                <span key={b} className={b === step.pressed ? "is-pressed" : undefined} style={b === step.pressed ? { ["--d" as string]: `${pressedAt}s` } : undefined}>
                  {b}
                </span>
              ))}
            </div>
          ))}
        </div>
      )}
      <div className="tg__home" />
    </div>
  );
}
