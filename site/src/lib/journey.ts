import config from "../../sensi.config";

export type ChatItem =
  | { kind: "bot"; text: string; buttons?: string[][] }
  | { kind: "user"; text: string }
  | { kind: "photos"; count: number }
  | { kind: "file"; name: string; size: string };

export type JourneyStep = {
  id: string;
  title: string;
  body: string;
  note?: string;
  chat: ChatItem[];
  keyboard?: string[][];
  pressed?: string;
  /** chat items (by index) shown in the phone-size step card; defaults to the last two */
  preview?: number[];
};

/** Mirrors the real bot conversation; edited in sensi.config.ts → journey.steps. */
export const journey = config.journey.steps as JourneyStep[];
