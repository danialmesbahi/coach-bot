import { notFound } from "next/navigation";
import ConsoleApp from "@/components/console-app";
import type { View } from "@/lib/types";

const views = new Set<View>(["orders", "messages", "customers", "sales"]);

export default async function ViewPage({ params }: { params: Promise<{ view: string }> }) {
  const { view } = await params;
  if (!views.has(view as View)) notFound();
  return <ConsoleApp initialView={view as View} />;
}
