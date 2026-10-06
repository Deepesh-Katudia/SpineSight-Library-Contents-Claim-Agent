// A procedurally generated bookshelf with a scanning beam. Pure CSS animation: each spine's
// highlight is delayed to the moment the beam crosses it.

const PALETTE = ["#7a1f1a", "#2f3d2c", "#1f2a3a", "#c9a24a", "#4a2c1f", "#d8cbb3", "#5b4636", "#33261d", "#8b5a2b", "#24302f"];
const TITLES = ["ULYSSES", "MIDDLEMARCH", "DUNE", "BELOVED", "", "EMMA", "THE WAVES", "SPQR", "", "PALE FIRE", "HOWARDS END", "ON BEAUTY", "", "WOLF HALL", "THE STRANGER", "SILENT SPRING", "", "GILEAD", "WATERSHIP DOWN", "BLEAK HOUSE"];
const BEAM_SECONDS = 7;
const SPINE_COUNT = 34;

interface Spine {
  heightPct: number;
  width: number;
  color: string;
  title: string;
  leftPct: number;
  cm: string;
}

function rand(seed: number): number {
  const x = Math.sin(seed * 9301 + 49297) * 233280;
  return x - Math.floor(x);
}

function buildShelf(): Spine[] {
  const spines: Spine[] = [];
  let x = 0;
  const widths = Array.from({ length: SPINE_COUNT }, (_, i) => 22 + Math.round(rand(i + 1) * 26));
  const total = widths.reduce((a, b) => a + b + 3, 0);
  widths.forEach((w, i) => {
    const heightPct = 62 + rand(i + 50) * 34;
    spines.push({
      heightPct,
      width: w,
      color: PALETTE[Math.floor(rand(i + 7) * PALETTE.length)],
      title: TITLES[i % TITLES.length],
      leftPct: ((x + w / 2) / total) * 100,
      cm: `${(17 + (heightPct - 62) / 34 * 9).toFixed(1)} × ${(w / 11).toFixed(1)}`,
    });
    x += w + 3;
  });
  return spines;
}

const SHELF = buildShelf();

export function HeroShelf() {
  return (
    <div className="relative w-full select-none" aria-hidden="true">
      <div className="relative flex h-[220px] items-end gap-[3px] overflow-hidden px-2 sm:h-[300px]">
        {SHELF.map((s, i) => {
          // the beam travels from -10% to 110% of the shelf width (see @keyframes scan)
          const delay = `${((s.leftPct + 10) / 120) * BEAM_SECONDS}s`;
          const unreadable = !s.title;
          return (
            <div
              key={i}
              className="group relative shrink-0 rounded-[2px]"
              style={{ height: `${s.heightPct}%`, width: s.width, background: s.color }}
            >
              <span
                className="absolute inset-x-0 top-1/2 -translate-y-1/2 whitespace-nowrap text-center font-mono text-[9px] tracking-[0.2em] text-paper/70 [writing-mode:vertical-rl]"
                style={{ color: s.color === "#d8cbb3" || s.color === "#c9a24a" ? "#100d0a99" : undefined }}
              >
                {s.title}
              </span>
              <span
                className="spine-box pointer-events-none absolute -inset-[3px] rounded-[3px] border opacity-0"
                style={{
                  borderColor: unreadable ? "var(--warn)" : "var(--signal)",
                  animation: `spine-hit ${BEAM_SECONDS}s linear ${delay} infinite`,
                }}
              />
              {i % 4 === 1 && (
                <span
                  className="pointer-events-none absolute -top-7 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-sm bg-ink-2 px-1.5 py-0.5 font-mono text-[9px] opacity-0"
                  style={{
                    color: unreadable ? "var(--warn)" : "var(--signal)",
                    animation: `spine-hit ${BEAM_SECONDS}s linear ${delay} infinite`,
                  }}
                >
                  {unreadable ? "unreadable · logged" : `${s.cm} cm`}
                </span>
              )}
            </div>
          );
        })}
        <div
          className="pointer-events-none absolute inset-y-0 left-0 w-full"
          style={{ animation: `scan ${BEAM_SECONDS}s linear infinite` }}
        >
          <div className="h-full w-[2px] bg-signal shadow-[0_0_24px_6px_rgba(255,107,44,0.45)]" />
        </div>
      </div>
      <div className="h-3 rounded-sm bg-gradient-to-b from-[#5b4636] to-[#2a1f16] shadow-[0_18px_40px_-10px_rgba(0,0,0,0.8)]" />
      <style>{`@keyframes spine-hit { 0% { opacity: 0 } 1% { opacity: 1 } 55% { opacity: 1 } 70% { opacity: 0.25 } 100% { opacity: 0.25 } }`}</style>
    </div>
  );
}
