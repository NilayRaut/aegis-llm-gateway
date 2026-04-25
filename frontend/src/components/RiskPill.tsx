const RISK = {
  SAFE:   { bg: '#EAF3DE', text: '#3B6D11', border: '#C5E0A4' },
  MEDIUM: { bg: '#FAEEDA', text: '#854F0B', border: '#F0CA8A' },
  HIGH:   { bg: '#FCEBEB', text: '#A32D2D', border: '#F5BBBB' },
}

export function RiskPill({ risk }: { risk: string }) {
  const s = RISK[risk as keyof typeof RISK] ?? RISK.SAFE
  return (
    <span
      className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border"
      style={{ background: s.bg, color: s.text, borderColor: s.border }}
    >
      {risk}
    </span>
  )
}
