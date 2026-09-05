export const metadata = {
  title: "Lead Engine",
  description: "Qualified leads for your sales team",
};

const css = `
  * { box-sizing: border-box; }
  body { margin: 0; font-family: -apple-system, system-ui, Segoe UI, Roboto, sans-serif;
         background: #0f1115; color: #e6e8eb; }
  a { color: inherit; }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 24px 16px 64px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  .sub { color: #9aa0a6; font-size: 13px; margin: 0 0 20px; }
  .bar { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 18px; }
  .bar input, .bar select { background: #1a1d23; color: #e6e8eb; border: 1px solid #2a2f37;
         border-radius: 8px; padding: 8px 10px; font-size: 13px; }
  .bar input { flex: 1; min-width: 180px; }
  .counts { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }
  .pill { font-size: 12px; padding: 4px 10px; border-radius: 999px; border: 1px solid #2a2f37; }
  .card { background: #1a1d23; border: 1px solid #2a2f37; border-radius: 12px;
          padding: 14px 16px; margin-bottom: 10px; }
  .card.HOT { border-left: 4px solid #ef4444; }
  .card.WARM { border-left: 4px solid #f59e0b; }
  .card.QUALIFIED { border-left: 4px solid #3b82f6; }
  .row1 { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .name { font-weight: 600; font-size: 15px; }
  .badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px; }
  .badge.HOT { background: #7f1d1d; color: #fecaca; }
  .badge.WARM { background: #78350f; color: #fde68a; }
  .badge.QUALIFIED { background: #1e3a8a; color: #bfdbfe; }
  .svc { font-size: 12px; color: #9aa0a6; }
  .score { margin-left: auto; font-size: 12px; color: #9aa0a6; }
  .want { margin: 8px 0 2px; font-size: 14px; }
  .why { font-size: 13px; color: #a5b4c3; }
  .ev { font-size: 12px; color: #7d848c; margin-top: 4px; }
  .actions { display: flex; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
  .call { background: #16a34a; color: #fff; text-decoration: none; padding: 6px 12px;
          border-radius: 8px; font-size: 13px; font-weight: 600; }
  .link { font-size: 12px; color: #60a5fa; text-decoration: none; }
  select.status { background:#12151a; }
  .status.done { border-color:#16a34a; }
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head><style dangerouslySetInnerHTML={{ __html: css }} /></head>
      <body><div className="wrap">{children}</div></body>
    </html>
  );
}
