// Hand-drawn SVG (rangoli, lights, diyas). Scales cleanly and no image licence to worry about.
function Rangoli({ cx, cy, r, opacity }: { cx: number; cy: number; r: number; opacity: number }) {
  const petals = Array.from({ length: 16 }, (_, i) => i * 22.5);
  const dots = Array.from({ length: 32 }, (_, i) => (i * 360) / 32);
  return (
    <g transform={`translate(${cx} ${cy})`} stroke="#F5C451" fill="none" opacity={opacity}>
      <circle r={r} strokeWidth={2} />
      <circle r={r * 0.82} strokeWidth={1.2} strokeDasharray="2 8" />
      {petals.map((a) => (
        <ellipse key={a} rx={r * 0.16} ry={r * 0.42} transform={`rotate(${a}) translate(0 ${-r * 0.42})`} strokeWidth={1.5} />
      ))}
      <circle r={r * 0.34} strokeWidth={1.5} />
      {petals.map((a) => (
        <path key={`s${a}`} d={`M0 ${-r * 0.12} L${r * 0.05} ${-r * 0.26} L0 ${-r * 0.34} L${-r * 0.05} ${-r * 0.26}Z`} transform={`rotate(${a + 11.25})`} strokeWidth={1.2} />
      ))}
      <circle r={r * 0.1} strokeWidth={2} />
      {dots.map((a) => (
        <circle key={`d${a}`} r={2.4} fill="#F5C451" stroke="none" transform={`rotate(${a}) translate(0 ${-r * 1.08})`} />
      ))}
    </g>
  );
}

function Diya({ x, y, s = 1 }: { x: number; y: number; s?: number }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <circle cy={-40} r={70} fill="url(#diya-glow)" />
      <path d="M-34 0 C-30 22 30 22 34 0 Z" fill="url(#diya-clay)" />
      <path d="M-36 0 H36" stroke="#7A2E0E" strokeWidth={3} strokeLinecap="round" />
      <path d="M0 -38 C10 -24 9 -10 0 -6 C-9 -10 -10 -24 0 -38 Z" fill="url(#flame)" />
      <path d="M0 -24 C4 -18 4 -11 0 -9 C-4 -11 -4 -18 0 -24 Z" fill="#FFF7D6" />
    </g>
  );
}

function Sparkle({ x, y, s }: { x: number; y: number; s: number }) {
  return <path d="M0 -10 L2 -2 L10 0 L2 2 L0 10 L-2 2 L-10 0 L-2 -2 Z" fill="#FFE29A" transform={`translate(${x} ${y}) scale(${s})`} opacity={0.75} />;
}

export function FestiveBackdrop({ className }: { className?: string }) {
  const bulbs = Array.from({ length: 15 }, (_, i) => {
    const t = i / 14;
    const x = -20 + t * 840;
    const y = 205 + Math.sin(t * Math.PI) * 55; // sagging string, below the logo
    return { x, y, warm: i % 3 !== 1 };
  });
  return (
    <svg className={className} viewBox="0 0 800 1000" preserveAspectRatio="xMidYMid slice" aria-hidden>
      <defs>
        <linearGradient id="bg-red" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#E8232A" />
          <stop offset="0.55" stopColor="#B5141B" />
          <stop offset="1" stopColor="#6E0A10" />
        </linearGradient>
        <radialGradient id="diya-glow">
          <stop offset="0" stopColor="#FFD36B" stopOpacity="0.55" />
          <stop offset="1" stopColor="#FFD36B" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="bulb-glow">
          <stop offset="0" stopColor="#FFE9A8" stopOpacity="0.9" />
          <stop offset="1" stopColor="#FFE9A8" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="diya-clay" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#E0782F" />
          <stop offset="1" stopColor="#9A3A12" />
        </linearGradient>
        <linearGradient id="flame" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#FFE07A" />
          <stop offset="1" stopColor="#FF8A1F" />
        </linearGradient>
        <radialGradient id="vignette" cx="0.5" cy="0.45" r="0.75">
          <stop offset="0.6" stopColor="#000" stopOpacity="0" />
          <stop offset="1" stopColor="#000" stopOpacity="0.35" />
        </radialGradient>
      </defs>

      <rect width="800" height="1000" fill="url(#bg-red)" />
      <Rangoli cx={690} cy={700} r={300} opacity={0.2} />
      <Rangoli cx={60} cy={380} r={150} opacity={0.12} />

      {/* lights. hidden in the phone banner, they'd cross the logo */}
      <g className="max-lg:hidden">
        <path d={`M-20 205 ${bulbs.map((b) => `L${b.x} ${b.y}`).join(' ')}`} stroke="#3B0A0D" strokeWidth={2} fill="none" opacity={0.6} />
        {bulbs.map((b, i) => (
          <g key={i} transform={`translate(${b.x} ${b.y + 10})`}>
            <circle r={26} fill="url(#bulb-glow)" opacity={b.warm ? 0.9 : 0.6} />
            <circle r={6} fill={b.warm ? '#FFE29A' : '#FFF4D6'} />
          </g>
        ))}
      </g>

      <Sparkle x={430} y={70} s={1.1} />
      <Sparkle x={660} y={120} s={0.8} />
      <Sparkle x={560} y={340} s={0.6} />
      <Sparkle x={250} y={520} s={0.7} />
      <Sparkle x={700} y={420} s={1} />

      {/* diyas */}
      <rect y="900" width="800" height="100" fill="#4A070B" opacity={0.35} />
      <Diya x={120} y={915} s={1} />
      <Diya x={290} y={925} s={1.25} />
      <Diya x={470} y={918} s={1.05} />
      <Diya x={650} y={928} s={1.3} />

      <rect width="800" height="1000" fill="url(#vignette)" />
    </svg>
  );
}
