import QRCode from "qrcode";

/** Server-rendered QR code as inline SVG, so desktop visitors can open the bot on their phone. */
export default async function Qr({ value, label }: { value: string; label: string }) {
  const svg = await QRCode.toString(value, { type: "svg", margin: 0, errorCorrectionLevel: "M", color: { dark: "#0b0c0e", light: "#0000" } });
  return <span className="qr" role="img" aria-label={label} dangerouslySetInnerHTML={{ __html: svg }} />;
}
