import { Bot, Code2, Globe, MessageCircle, PhoneCall, Smartphone } from "lucide-react";

/** One glyph per thing you sell, shared by the card and the detail page.
 *  No "use client": both server and client components import this. */
const ICONS: Record<string, typeof Globe> = {
  website: Globe,
  chatbot: Bot,
  whatsapp_bot: MessageCircle,
  ai_phone: PhoneCall,
  mobile_app: Smartphone,
  custom_software: Code2,
};

export default function ServiceIcon({ service, size = 13 }: { service: string | null; size?: number }) {
  const Icon = ICONS[service ?? ""] ?? Code2;
  return <Icon size={size} strokeWidth={1.75} />;
}
