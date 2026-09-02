import { useState, useEffect, useRef, useCallback } from "react";
import {
  TrendingUp, Target, Shield, BarChart3, CheckCircle2,
  AlertTriangle, Download, Activity, MessageSquare, X, Send,
  Sparkles, Upload, RefreshCw, Rocket,
} from "lucide-react";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";

// ─── Avatar ───────────────────────────────────────────────────────────────────
const AVATAR_SEEDS = ["Mia","Leo","Zoe","Rex","Ivy","Max","Ada","Jay","Nia","Sam"];
const AVATAR_BG    = ["b6e3f4","c0aede","d1d4f9","ffd5dc","ffdfbf","c1f4c5","fef3b4","f4b8c1","b5ead7","e2b4f4"];

function Avatar({ seed, size = 36, border = "#fff", index = 0 }: {
  seed: string; size?: number; border?: string; index?: number;
}) {
  const bg = AVATAR_BG[index % AVATAR_BG.length];
  return (
    <img
      src={`https://api.dicebear.com/9.x/adventurer/svg?seed=${seed}&backgroundColor=${bg}&radius=50`}
      alt={seed}
      width={size} height={size}
      style={{
        width: size, height: size, borderRadius: "50%",
        border: `2.5px solid ${border}`,
        objectFit: "cover",
        display: "block",
        boxShadow: "0 2px 8px rgba(0,0,0,0.1)",
        background: `#${bg}`,
      }}
    />
  );
}

function AvatarStack({ seeds, size = 34, overlap = 10 }: { seeds: string[]; size?: number; overlap?: number }) {
  return (
    <div style={{ display: "flex", alignItems: "center" }}>
      {seeds.map((s, i) => (
        <div key={s} style={{ marginLeft: i === 0 ? 0 : -overlap, zIndex: seeds.length - i, position: "relative" }}>
          <Avatar seed={s} size={size} index={i} />
        </div>
      ))}
    </div>
  );
}

// ─── Types ────────────────────────────────────────────────────────────────────
type Stage = { id: string; label: string; emoji: string; done: boolean; active: boolean; count?: number };
type MatchRow = {
  id: string;
  bank: string;
  ledger: string;       // comma-joined ledger IDs
  amount: string;
  tier: string;         // "Tier 1" | "Tier 2" | "Tier 3"
  matchType: string;    // "1:1" | "1:N" | "N:1" | "N:M"
  confidence: number;   // 0-100
  llmSource?: string;   // "ollama" | "gemini" | "heuristic" | null
  date: string;
};
type ExcRow = { id: string; record: string; amount: string; reason: string; code: string };
type ChatMsg = { role: "user" | "ai"; text: string; ts: string };
type LiveStats = { matches: number; total_bank_records: number; precision: number; recall: number; f1_score: number; exceptions: number; match_type_counts?: Record<string,number> };

// ─── Data ─────────────────────────────────────────────────────────────────────
const STAGES: Stage[] = [
  { id: "blocking",  label: "Blocking",     emoji: "🔍", done: false, active: false },
  { id: "normalize", label: "Normalize",    emoji: "⚡", done: false, active: false },
  { id: "tier1",     label: "Tier 1 Match", emoji: "🎯", done: false, active: false, count: 0 },
  { id: "tier2",     label: "Tier 2 Match", emoji: "🤝", done: false, active: false, count: 0 },
  { id: "tier3",     label: "AI Match",     emoji: "✨", done: false, active: false, count: 0 },
];

const TIER_COLORS: Record<string, string> = { "Tier 1": "#0ea5e9", "Tier 2": "#818cf8", "Tier 3": "#f472b6" };
const MATCH_TYPE_META: Record<string, { color: string; bg: string; label: string }> = {
  "1:1": { color: "#0ea5e9", bg: "#f0f9ff",  label: "1:1"  },
  "1:N": { color: "#818cf8", bg: "#eef2ff",  label: "1:N"  },
  "N:1": { color: "#f472b6", bg: "#fdf2f8",  label: "N:1"  },
  "N:M": { color: "#f59e0b", bg: "#fffbeb",  label: "N:M"  },
};
const LLM_SOURCE_META: Record<string, { color: string; bg: string; label: string }> = {
  ollama:    { color: "#16a34a", bg: "#f0fdf4",  label: "🦙 Ollama"   },
  gemini:    { color: "#0369a1", bg: "#f0f9ff",  label: "✨ Gemini"   },
  heuristic: { color: "#92400e", bg: "#fef9ee",  label: "📏 Heuristic" },
};
const CODE_META: Record<string, { color: string; bg: string; dot: string; emoji: string }> = {
  NO_MATCH:              { color: "#64748b", bg: "#f8fafc", dot: "#ef4444", emoji: "❓" },
  NO_CANDIDATE:          { color: "#64748b", bg: "#f8fafc", dot: "#ef4444", emoji: "❓" },
  AMT_DELTA:             { color: "#92400e", bg: "#fef9ee", dot: "#f59e0b", emoji: "💰" },
  DUPLICATE:             { color: "#5b21b6", bg: "#f5f3ff", dot: "#8b5cf6", emoji: "🔄" },
  DATE_SLIP:             { color: "#9a3412", bg: "#fff8f5", dot: "#fb923c", emoji: "📅" },
  VOID_OPEN:             { color: "#0369a1", bg: "#f0f9ff", dot: "#38bdf8", emoji: "✕"  },
  FS_WEIGHT_LOW:         { color: "#0f172a", bg: "#f8fafc", dot: "#94a3b8", emoji: "⚖️" },
  AMBIGUOUS_MULTI:       { color: "#5b21b6", bg: "#f5f3ff", dot: "#8b5cf6", emoji: "🔀" },
  UNKNOWN_EXCEPTION:     { color: "#64748b", bg: "#f8fafc", dot: "#94a3b8", emoji: "⚠️" },
  LLM_UNRESOLVED:        { color: "#9a3412", bg: "#fff8f5", dot: "#f97316", emoji: "🤖" },
  NO_UNCONSUMED_CANDIDATES: { color: "#64748b", bg: "#f8fafc", dot: "#94a3b8", emoji: "🗑️" },
};
const DEFAULT_CODE_META = { color: "#64748b", bg: "#f8fafc", dot: "#94a3b8", emoji: "⚠️" };

const CANNED: Record<string, string> = {
  default:   "Most exceptions come from timing differences between bank clearance and ledger posting.",
  exception: "Check NO_CANDIDATE exceptions first — they indicate records with no ledger counterpart.",
  match:     "Tier 1 handles exact matches, Tier 2 uses Jaro-Winkler + Fellegi-Sunter weights, Tier 3 uses Ollama (Qwen2.5) with Gemini as fallback.",
  tier:      "Tier 1: exact amount+date. Tier 2: fuzzy JW ≥ 0.85 + FS weight. Tier 3: LLM (Ollama primary, Gemini fallback). 1:N/N:1/N:M group matching runs after 1:1 pass.",
};

// ─── Hooks ────────────────────────────────────────────────────────────────────
function useCountUp(target: number, active: boolean, dur = 1400) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (!active) return;
    const t0 = performance.now();
    const frame = (now: number) => {
      const p = Math.min((now - t0) / dur, 1);
      setVal(Math.floor((1 - Math.pow(1 - p, 4)) * target));
      if (p < 1) requestAnimationFrame(frame); else setVal(target);
    };
    requestAnimationFrame(frame);
  }, [target, active, dur]);
  return val;
}

function useInView(ref: React.RefObject<Element | null>) {
  const [v, setV] = useState(false);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setV(true); obs.disconnect(); } }, { threshold: 0.1 });
    obs.observe(el); return () => obs.disconnect();
  }, []);
  return v;
}

// ─── Confetti ─────────────────────────────────────────────────────────────────
type Piece = { id: number; x: number; color: string; size: number; delay: number };
function Confetti({ active }: { active: boolean }) {
  const [pieces, setPieces] = useState<Piece[]>([]);
  useEffect(() => {
    if (!active) return;
    const colors = ["#38bdf8", "#818cf8", "#f472b6", "#34d399", "#fb923c", "#facc15", "#fff"];
    setPieces(Array.from({ length: 70 }, (_, i) => ({
      id: i, x: Math.random() * 100,
      color: colors[Math.floor(Math.random() * colors.length)],
      size: Math.random() * 9 + 5, delay: Math.random() * 1.4,
    })));
    const t = setTimeout(() => setPieces([]), 4000);
    return () => clearTimeout(t);
  }, [active]);
  if (!pieces.length) return null;
  return (
    <div style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 999, overflow: "hidden" }}>
      {pieces.map(p => (
        <div key={p.id} style={{
          position: "absolute", left: `${p.x}%`, top: 0,
          width: p.size, height: p.size, borderRadius: p.id % 2 === 0 ? "50%" : 3,
          background: p.color, opacity: 0.9,
          animation: `confetti-fall ${2.2 + Math.random() * 1.2}s cubic-bezier(0.25,0.46,0.45,0.94) ${p.delay}s forwards`,
        }} />
      ))}
    </div>
  );
}

// ─── Wave divider ─────────────────────────────────────────────────────────────
function WaveDivider() {
  return (
    <div style={{ position: "relative", width: "100%", marginTop: -2, lineHeight: 0 }}>
      <svg viewBox="0 0 1440 90" fill="none" xmlns="http://www.w3.org/2000/svg"
        style={{ width: "100%", display: "block" }}>
        <path
          d="M0,40 C200,80 400,10 600,45 C800,80 1000,15 1200,50 C1320,68 1380,55 1440,48 L1440,90 L0,90 Z"
          fill="#f0f7ff"
        />
      </svg>
    </div>
  );
}

// ─── Top Nav ──────────────────────────────────────────────────────────────────
function TopNav({ onChat, activeTab, onChangeTab }: { onChat: () => void; activeTab: string; onChangeTab: (t: string) => void }) {
  return (
    <nav className="anim-fade-in" style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "18px 40px",
      background: "#fff",
      borderBottom: "1px solid #f1f5f9",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 12,
          background: "rgba(255,255,255,0.25)",
          backdropFilter: "blur(8px)",
          border: "1px solid rgba(255,255,255,0.4)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 18,
          boxShadow: "0 2px 12px rgba(14,165,233,0.15)",
        }}>💰</div>
        <span style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 16, fontWeight: 800, color: "#0f172a", letterSpacing: "-0.02em" }}>
          Fin<span style={{ color: "#0ea5e9" }}>flow</span>
        </span>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        {["Dashboard", "Reports", "Audit", "Settings"].map(item => (
          <button key={item} onClick={() => onChangeTab(item)} style={{
            padding: "7px 16px", borderRadius: 20, background: item === activeTab ? "rgba(255,255,255,0.35)" : "transparent",
            border: "none", cursor: "pointer",
            color: item === activeTab ? "#0f172a" : "rgba(15,23,42,0.5)",
            fontSize: 13, fontFamily: "'Inter',sans-serif", fontWeight: item === activeTab ? 600 : 400,
            transition: "all 0.2s",
            backdropFilter: item === activeTab ? "blur(8px)" : "none",
            boxShadow: item === activeTab ? "0 1px 4px rgba(0,0,0,0.08)" : "none",
          }}
            onMouseEnter={e => { if (item !== activeTab) (e.currentTarget as HTMLButtonElement).style.color = "#0f172a"; }}
            onMouseLeave={e => { if (item !== activeTab) (e.currentTarget as HTMLButtonElement).style.color = "rgba(15,23,42,0.5)"; }}
          >{item}</button>
        ))}
        <button onClick={onChat} style={{
          padding: "9px 20px", borderRadius: 24,
          background: "#0f172a",
          border: "none", cursor: "pointer", color: "#fff",
          fontSize: 13, fontWeight: 600, fontFamily: "'Inter',sans-serif",
          display: "flex", alignItems: "center", gap: 7,
          boxShadow: "0 4px 16px rgba(15,23,42,0.25)",
          transition: "all 0.25s cubic-bezier(0.22,1,0.36,1)",
        }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1.04) translateY(-1px)"; (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 8px 24px rgba(15,23,42,0.3)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)"; (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 4px 16px rgba(15,23,42,0.25)"; }}
        >
          <MessageSquare size={13} /> Ask AI
        </button>

        {/* User avatar chip */}
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "4px 12px 4px 4px", borderRadius: 24,
          background: activeTab === "Profile" ? "rgba(255,255,255,0.8)" : "rgba(255,255,255,0.4)", 
          backdropFilter: "blur(8px)",
          border: "1px solid rgba(255,255,255,0.6)",
          cursor: "pointer",
          transition: "background 0.2s",
        }}
          onClick={() => onChangeTab("Profile")}
          onMouseEnter={e => { if (activeTab !== "Profile") (e.currentTarget.style.background = "rgba(255,255,255,0.6)") }}
          onMouseLeave={e => { if (activeTab !== "Profile") (e.currentTarget.style.background = "rgba(255,255,255,0.4)") }}
        >
          <Avatar seed="Sam" size={28} border="rgba(255,255,255,0.8)" index={9} />
          <span style={{ fontSize: 12, fontWeight: 600, color: "#0f172a", fontFamily: "'Inter',sans-serif" }}>Sam</span>
        </div>
      </div>
    </nav>
  );
}

// ─── Hero section ─────────────────────────────────────────────────────────────
function Hero({ onRun, running, liveStats }: { onRun: () => void; running: boolean; liveStats: LiveStats | null }) {
  return (
    <div style={{
      background: "linear-gradient(160deg, #bae6fd 0%, #93c5fd 40%, #c7d2fe 100%)",
      paddingBottom: 0,
    }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", padding: "20px 40px 0", gap: 32, minHeight: 420 }}>
        {/* Left: headline */}
        <div className="anim-slide-up" style={{ maxWidth: 520, paddingBottom: 48 }}>
          <div style={{
            display: "inline-flex", alignItems: "center", gap: 7,
            padding: "5px 14px", borderRadius: 20,
            background: "rgba(255,255,255,0.35)", backdropFilter: "blur(8px)",
            border: "1px solid rgba(255,255,255,0.5)",
            fontSize: 12, color: "#0369a1", fontWeight: 600,
            fontFamily: "'Inter',sans-serif", marginBottom: 22,
          }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#0ea5e9", display: "inline-block" }} />
            Live reconciliation engine
          </div>

          <h1 style={{
            fontFamily: "'Plus Jakarta Sans',sans-serif",
            fontSize: "clamp(36px, 5vw, 58px)", fontWeight: 800,
            color: "#0f172a", margin: "0 0 16px", lineHeight: 1.15,
            letterSpacing: "-0.03em",
          }}>
            Smart Finance<br />
            <span className="retro-text" style={{
              fontFamily: "'Plus Jakarta Sans',sans-serif",
              fontWeight: 900,
              display: "inline-block",
              marginTop: 6,
            }}>
              Reconciliation.
            </span>
          </h1>
          <p style={{
            color: "rgba(15,23,42,0.55)", fontSize: 15,
            fontFamily: "'Inter',sans-serif", lineHeight: 1.7,
            margin: "0 0 32px", maxWidth: 400,
          }}>
            Upload your bank and ledger CSVs. Our 3-tier AI engine matches records in seconds, so you can focus on the exceptions that matter.
          </p>

          <button onClick={onRun} disabled={running} style={{
            display: "inline-flex", alignItems: "center", gap: 9,
            padding: "14px 28px", borderRadius: 50,
            background: "#0f172a",
            border: "none", cursor: running ? "not-allowed" : "pointer",
            color: "#fff", fontWeight: 700, fontSize: 15,
            fontFamily: "'Plus Jakarta Sans',sans-serif",
            boxShadow: "0 8px 28px rgba(15,23,42,0.28)",
            transition: "all 0.3s cubic-bezier(0.22,1,0.36,1)",
            opacity: running ? 0.7 : 1,
            letterSpacing: "-0.01em",
          }}
            onMouseEnter={e => { if (!running) { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1.04) translateY(-2px)"; (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 14px 36px rgba(15,23,42,0.35)"; } }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)"; (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 8px 28px rgba(15,23,42,0.28)"; }}
          >
            {running
              ? <><RefreshCw size={16} style={{ animation: "spin 1s linear infinite" }} /> Running…</>
              : <><Rocket size={16} /> Run Demo — 60 records</>
            }
          </button>

          {/* Social proof avatar row */}
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 24 }}>
            <AvatarStack seeds={["Mia","Leo","Zoe","Rex","Ivy"]} size={36} overlap={12} />
            <div>
              <div style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontWeight: 900, fontSize: 15, lineHeight: 1 }}>
                <span style={{ fontSize: 18, color: "#0ea5e9", fontWeight: 900 }}>2,400+</span>
                <span style={{ color: "#0f172a", fontWeight: 700, fontSize: 13, marginLeft: 4 }}>finance teams</span>
              </div>
              <div style={{ fontSize: 11, color: "rgba(15,23,42,0.5)", fontWeight: 500, marginTop: 3 }}>
                trust Finflow to reconcile every month
              </div>
            </div>
          </div>
        </div>

        {/* Right: mascot images + floating stat chips */}
        <div className="anim-slide-up" style={{
          animationDelay: "0.12s",
          position: "relative",
          width: 460, flexShrink: 0,
          height: 400,
          display: "flex", alignItems: "flex-end",
        }}>
          {/* Main mascot — cute toy character */}
          <img
            src="https://images.unsplash.com/photo-1638803040283-7a5ffd48dad5?w=440&h=560&fit=crop&crop=top&auto=format&q=85"
            alt="Cute mascot character"
            className="float-anim"
            style={{
              position: "absolute",
              bottom: 0, left: "50%",
              transform: "translateX(-50%)",
              width: 230, height: 310,
              objectFit: "cover",
              objectPosition: "center top",
              borderRadius: 36,
              boxShadow: "0 28px 72px rgba(14,165,233,0.25), 0 8px 28px rgba(0,0,0,0.13)",
              border: "3px solid rgba(255,255,255,0.8)",
              animationDelay: "0s",
              animationDuration: "4s",
            }}
          />

          {/* Secondary — pink piggy bank */}
          <img
            src="https://images.unsplash.com/photo-1607863680198-23d4b2565df0?w=300&h=300&fit=crop&crop=center&auto=format&q=85"
            alt="Pink piggy bank"
            className="float-anim"
            style={{
              position: "absolute",
              bottom: 28, right: 0,
              width: 144, height: 144,
              objectFit: "cover",
              objectPosition: "center",
              borderRadius: 28,
              boxShadow: "0 16px 40px rgba(244,114,182,0.2), 0 4px 16px rgba(0,0,0,0.1)",
              border: "3px solid rgba(255,255,255,0.9)",
              animationDelay: "0.8s",
              animationDuration: "5s",
            }}
          />

          {/* Third accent — ceramic piggy bank */}
          <img
            src="https://images.unsplash.com/photo-1580508174046-170816f65662?w=220&h=220&fit=crop&crop=center&auto=format&q=85"
            alt="Ceramic piggy bank"
            className="float-anim"
            style={{
              position: "absolute",
              top: 16, left: 4,
              width: 104, height: 104,
              objectFit: "cover",
              objectPosition: "center",
              borderRadius: 22,
              boxShadow: "0 12px 32px rgba(244,114,182,0.18), 0 4px 12px rgba(0,0,0,0.09)",
              border: "3px solid rgba(255,255,255,0.9)",
              animationDelay: "1.4s",
              animationDuration: "3.5s",
            }}
          />

          {/* Floating stat chips */}
          {[
            { label: "Match rate", value: liveStats ? `${Math.round((liveStats.matches / Math.max(1, liveStats.total_bank_records)) * 100)}%` : "—", icon: "🎯", top: 6,   right: 148, delay: "0s" },
            { label: "Records",    value: liveStats ? String(liveStats.total_bank_records) : "—",     icon: "📋", top: 152, left: 0,   delay: "0.25s" },
            { label: "Exceptions", value: liveStats ? String(liveStats.exceptions) : "—",   icon: "⚡", bottom: 40, right: 0, delay: "0.5s" },
          ].map(chip => (
            <div key={chip.label} className="float-anim" style={{
              position: "absolute",
              top: chip.top, bottom: (chip as any).bottom,
              left: (chip as any).left, right: (chip as any).right,
              background: "rgba(255,255,255,0.72)",
              backdropFilter: "blur(16px)",
              border: "1.5px solid rgba(255,255,255,0.9)",
              borderRadius: 16, padding: "10px 16px",
              display: "flex", alignItems: "center", gap: 10,
              boxShadow: "0 8px 24px rgba(14,165,233,0.12), 0 1px 0 rgba(255,255,255,0.9) inset",
              animationDelay: chip.delay,
              animationDuration: "4.5s",
              zIndex: 10,
            }}>
              <span style={{ fontSize: 20 }}>{chip.icon}</span>
              <div>
                <div style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontWeight: 800, fontSize: 17, color: "#0f172a", letterSpacing: "-0.02em", lineHeight: 1 }}>{chip.value}</div>
                <div style={{ fontSize: 10, color: "rgba(15,23,42,0.45)", fontWeight: 500, marginTop: 2 }}>{chip.label}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Upload Zone ──────────────────────────────────────────────────────────────
function UploadZone({ onRun, running }: { onRun: (files: File[]) => void; running: boolean }) {
  const [drag, setDrag] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [sizeError, setSizeError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const v = useInView(ref);

  const handleFiles = (newFiles: File[]) => {
    if (newFiles.some(f => f.size > 100 * 1024 * 1024)) {
      setSizeError("Files must be under 100MB.");
      return;
    }
    setSizeError(null);
    setFiles(newFiles);
  };

  // Allow running with no files (uses demo data); single file also valid (BenchRec)
  const isReady = true;

  return (
    <div ref={ref} className={v ? "anim-bounce-in" : ""} style={{ opacity: v ? undefined : 0, animationDelay: "0.1s" }}>
      <div style={{
        background: "#fff", borderRadius: 24,
        border: "1px solid #e2e8f0",
        padding: "28px",
        boxShadow: "0 4px 24px rgba(14,165,233,0.06), 0 1px 2px rgba(0,0,0,0.04)",
        height: "100%",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
          <div style={{ width: 32, height: 32, borderRadius: 10, background: "#f0f9ff", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Upload size={15} color="#0ea5e9" />
          </div>
          <span style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontWeight: 700, fontSize: 14, color: "#0f172a" }}>Upload Files</span>
        </div>

        <div
          onClick={() => fileInputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDrag(true); }}
          onDragLeave={() => setDrag(false)}
          onDrop={e => { e.preventDefault(); setDrag(false); handleFiles(Array.from(e.dataTransfer.files)); }}
          style={{
            border: `2px dashed ${drag ? "#0ea5e9" : "#e2e8f0"}`,
            borderRadius: 16, padding: "28px 20px", textAlign: "center",
            background: drag ? "#f0f9ff" : "#fafafa",
            transition: "all 0.25s",
            transform: drag ? "scale(1.02)" : "scale(1)",
            cursor: "pointer", marginBottom: 16,
          }}
        >
          <div style={{ fontSize: 30, marginBottom: 10, transition: "transform 0.3s", transform: drag ? "scale(1.15) rotate(-6deg)" : "scale(1)" }}>
            {files.length ? "✅" : drag ? "🎯" : "☁️"}
          </div>
          {files.length > 0
            ? files.map(f => <div key={f.name} style={{ fontSize: 12, color: "#0ea5e9", fontFamily: "'JetBrains Mono',monospace", marginBottom: 2 }}>✓ {f.name}</div>)
            : <>
                <p style={{ color: "#94a3b8", fontSize: 13, margin: "0 0 4px" }}>
                  Drop <span style={{ color: "#0f172a", fontWeight: 600 }}>bank.csv</span> &amp; <span style={{ color: "#0f172a", fontWeight: 600 }}>ledger.csv</span>, or a single <span style={{ color: "#0f172a", fontWeight: 600 }}>combined file</span>
                </p>
                <p style={{ color: "#cbd5e1", fontSize: 11, margin: 0 }}>or click to browse</p>
              </>
          }
          <input
            type="file"
            multiple
            accept=".csv"
            ref={fileInputRef}
            style={{ display: "none" }}
            onChange={e => {
              if (e.target.files && e.target.files.length > 0) {
                handleFiles(Array.from(e.target.files));
              }
            }}
          />
        </div>

        <button onClick={() => onRun(files)} disabled={running || !isReady} style={{
          width: "100%", padding: "13px 20px", borderRadius: 50,
          background: (running || !isReady) ? "#e2e8f0" : "#0f172a",
          border: "none", cursor: (running || !isReady) ? "not-allowed" : "pointer",
          color: (running || !isReady) ? "#94a3b8" : "#fff",
          fontWeight: 700, fontSize: 14,
          fontFamily: "'Plus Jakarta Sans',sans-serif",
          display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
          boxShadow: running ? "none" : "0 4px 16px rgba(15,23,42,0.2)",
          transition: "all 0.25s",
        }}
          onMouseEnter={e => { if (!running && isReady) { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1.02)"; (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 8px 24px rgba(15,23,42,0.28)"; } }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)"; (e.currentTarget as HTMLButtonElement).style.boxShadow = (running || !isReady) ? "none" : "0 4px 16px rgba(15,23,42,0.2)"; }}
        >
          {running
            ? <><RefreshCw size={14} style={{ animation: "spin 1s linear infinite" }} /> Matching…</>
            : files.length > 0
              ? <><Rocket size={14} /> Run Reconciliation</>
              : <><Rocket size={14} /> Run Demo</>
          }
        </button>
        {sizeError && <div style={{ color: "#ef4444", fontSize: 12, marginTop: 10, textAlign: "center", fontWeight: 500 }}>{sizeError}</div>}
        {files.length === 1 && <div style={{ color: "#0ea5e9", fontSize: 11, marginTop: 10, textAlign: "center", fontWeight: 500 }}>Single file detected — will auto-split A/B sides (BenchRec format)</div>}
      </div>
    </div>
  );
}

// ─── Pipeline ─────────────────────────────────────────────────────────────────
function PipelineProgress({ stages }: { stages: Stage[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const v = useInView(ref);
  const done = stages.filter(s => s.done).length;
  const pct = Math.round((done / stages.length) * 100);
  const [disp, setDisp] = useState(0);
  const prevAvatarIdx = useRef(0);
  const [avatarSnap, setAvatarSnap] = useState(false);

  useEffect(() => {
    const id = setInterval(() => setDisp(p => p >= pct ? (clearInterval(id), pct) : Math.min(p + 2, pct)), 16);
    return () => clearInterval(id);
  }, [pct]);

  const VW = 600, VH = 200;
  const nodes = [
    { x: 80,  y: 78  },
    { x: 200, y: 148 },
    { x: 320, y: 78  },
    { x: 440, y: 148 },
    { x: 560, y: 78  },
  ];
  const segments = [
    "M 80,78 C 130,78 150,148 200,148",
    "M 200,148 C 250,148 270,78 320,78",
    "M 320,78 C 370,78 390,148 440,148",
    "M 440,148 C 490,148 510,78 560,78",
  ];
  const activeIdx = stages.findIndex(s => s.active);
  const avatarIdx = activeIdx >= 0 ? activeIdx : Math.min(done, stages.length - 1);
  const isTop = (i: number) => i % 2 === 0;

  useEffect(() => {
    if (avatarIdx < prevAvatarIdx.current) {
      setAvatarSnap(true);
      const t = setTimeout(() => setAvatarSnap(false), 50);
      prevAvatarIdx.current = avatarIdx;
      return () => clearTimeout(t);
    }
    prevAvatarIdx.current = avatarIdx;
  }, [avatarIdx]);

  return (
    <div ref={ref} className={v ? "anim-bounce-in" : ""} style={{ opacity: v ? undefined : 0, animationDelay: "0.18s" }}>
      <div style={{
        background: "#fff", borderRadius: 24,
        border: "1px solid #e2e8f0",
        padding: "24px 28px", height: "100%",
        boxShadow: "0 4px 24px rgba(14,165,233,0.05), 0 1px 2px rgba(0,0,0,0.04)",
      }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 32, height: 32, borderRadius: 10, background: "#f8fafc", border: "1px solid #e2e8f0", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Activity size={15} color="#64748b" />
            </div>
            <span style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontWeight: 700, fontSize: 14, color: "#0f172a" }}>Pipeline Progress</span>
          </div>
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 5,
            padding: "3px 10px", borderRadius: 6, fontSize: 11, fontWeight: 600,
            background: "#f8fafc", color: pct === 100 ? "#16a34a" : "#64748b",
            border: "1px solid #e2e8f0", fontFamily: "'JetBrains Mono',monospace", transition: "color 0.5s",
          }}>
            {pct === 100 && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#16a34a", display: "inline-block" }} />}
            {pct === 100 ? "Complete" : `${disp}%`}
          </span>
        </div>

        {/* Winding road map */}
        <div style={{ position: "relative", width: "100%", paddingBottom: `${(VH / VW) * 100}%` }}>
          <div style={{ position: "absolute", inset: 0 }}>
            <svg viewBox={`0 0 ${VW} ${VH}`} style={{ width: "100%", height: "100%", overflow: "visible" }}>
              {/* Background road track */}
              {segments.map((d, i) => (
                <path key={`bg-${i}`} d={d} fill="none" stroke="#f1f5f9" strokeWidth={14} strokeLinecap="round" />
              ))}
              {/* Road center dashes */}
              {segments.map((d, i) => (
                <path key={`dash-${i}`} d={d} fill="none" stroke="#e8ecf0" strokeWidth={2}
                  strokeLinecap="round" strokeDasharray="12 9" />
              ))}
              {/* Completed road segments */}
              {segments.map((d, i) =>
                stages[i]?.done ? (
                  <path key={`done-${i}`} d={d} fill="none" stroke="#0f172a" strokeWidth={14}
                    strokeLinecap="round" style={{ animation: "fade-in 0.4s ease" }} />
                ) : null
              )}
              {/* Stage nodes */}
              {stages.map((s, i) => {
                const n = nodes[i];
                const top = isTop(i);
                return (
                  <g key={s.id}>
                    {/* Node */}
                    <circle cx={n.x} cy={n.y} r={18}
                      fill={s.done ? "#0f172a" : "#fff"}
                      stroke={s.done ? "#0f172a" : s.active ? "#0f172a" : "#e2e8f0"}
                      strokeWidth={s.active ? 2.5 : 2}
                      style={{ transition: "fill 0.4s, stroke 0.4s" }}
                    />
                    {s.done ? (
                      <path d={`M ${n.x-6} ${n.y} L ${n.x-2} ${n.y+5} L ${n.x+7} ${n.y-6}`}
                        stroke="#fff" strokeWidth={2.5} fill="none" strokeLinecap="round" strokeLinejoin="round"
                        style={{ animation: "fade-in 0.3s ease" }}
                      />
                    ) : (
                      <text x={n.x} y={n.y + 4.5} textAnchor="middle" fontSize={12} fontWeight="600"
                        fill={s.active ? "#0f172a" : "#cbd5e1"} fontFamily="Inter, sans-serif"
                      >{i + 1}</text>
                    )}
                    {/* Label */}
                    <text x={n.x} y={top ? n.y - 27 : n.y + 35}
                      textAnchor="middle" fontSize={9.5}
                      fontWeight={s.done || s.active ? "600" : "400"}
                      fill={s.done ? "#0f172a" : s.active ? "#0f172a" : "#94a3b8"}
                      fontFamily="Inter, sans-serif"
                      style={{ transition: "fill 0.4s" }}
                    >{s.label}</text>
                    {/* Count badge */}
                    {s.count !== undefined && s.count > 0 && (
                      <g style={{ animation: "bounce-in 0.35s cubic-bezier(0.22,1,0.36,1)" }}>
                        <rect x={n.x - 18} y={top ? n.y - 54 : n.y + 42} width={36} height={16} rx={4}
                          fill="#f8fafc" stroke="#e2e8f0" strokeWidth={1} />
                        <text x={n.x} y={top ? n.y - 43 : n.y + 53}
                          textAnchor="middle" fontSize={8.5} fontWeight="700"
                          fill="#64748b" fontFamily="'JetBrains Mono', monospace"
                        >+{s.count}</text>
                      </g>
                    )}
                  </g>
                );
              })}
              
              {/* Floating avatar — follows exact road path */}
              <image
                href={`https://api.dicebear.com/9.x/adventurer/svg?seed=Finley&backgroundColor=c0aede&radius=50`}
                x="-17" y="-17" width="34" height="34"
                className="float-anim"
                style={{
                  offsetPath: "path('M 80,78 C 130,78 150,148 200,148 C 250,148 270,78 320,78 C 370,78 390,148 440,148 C 490,148 510,78 560,78')",
                  offsetDistance: `${(avatarIdx / 4) * 100}%`,
                  transition: avatarSnap ? "none" : "offset-distance 1.3s cubic-bezier(0.4,0,0.2,1)",
                  pointerEvents: "none"
                }}
              />
            </svg>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Metric Card ──────────────────────────────────────────────────────────────
function MetricCard({ label, value, unit, icon: Icon, color, bg, active, delay }: {
  label: string; value: number; unit: string; icon: React.FC<any>; color: string; bg: string; active: boolean; delay: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const v = useInView(ref);
  const disp = useCountUp(value, active);
  const [hov, setHov] = useState(false);

  return (
    <div ref={ref} className={v ? "anim-bounce-in" : ""} style={{ opacity: v ? undefined : 0, animationDelay: `${delay}s` }}>
      <div
        onMouseEnter={() => setHov(true)}
        onMouseLeave={() => setHov(false)}
        style={{
          background: "#fff", borderRadius: 24,
          border: `1.5px solid ${hov ? color + "40" : "#e2e8f0"}`,
          padding: "24px",
          boxShadow: hov
            ? `0 12px 40px rgba(0,0,0,0.08), 0 0 0 4px ${color}10`
            : "0 4px 24px rgba(14,165,233,0.05), 0 1px 2px rgba(0,0,0,0.04)",
          transition: "all 0.3s cubic-bezier(0.22,1,0.36,1)",
          transform: hov ? "translateY(-4px)" : "translateY(0)",
          cursor: "default", position: "relative", overflow: "hidden",
        }}
      >
        <div style={{
          position: "absolute", top: -16, right: -16, width: 80, height: 80,
          background: `radial-gradient(circle, ${color}18 0%, transparent 70%)`,
          transition: "opacity 0.3s", opacity: hov ? 1 : 0.5,
        }} />
        <div style={{
          width: 40, height: 40, borderRadius: 14, background: bg,
          display: "flex", alignItems: "center", justifyContent: "center",
          marginBottom: 18,
          boxShadow: hov ? `0 4px 16px ${color}30` : "none",
          transition: "box-shadow 0.3s",
        }}>
          <Icon size={18} color={color} />
        </div>
        <div style={{
          fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 40, fontWeight: 900,
          lineHeight: 1, letterSpacing: "-0.04em", marginBottom: 10,
          animation: active ? "count-up 0.5s ease-out" : "none",
        }}>
          {active
            ? <>
                <span style={{
                  background: `linear-gradient(135deg, ${color} 0%, ${color}bb 100%)`,
                  WebkitBackgroundClip: "text",
                  WebkitTextFillColor: "transparent",
                  backgroundClip: "text",
                  display: "inline-block",
                }}>{disp}</span>
                <span style={{ fontSize: 15, marginLeft: 3, fontWeight: 600, color: "#94a3b8", display: "inline-block", WebkitTextFillColor: "#94a3b8" }}>{unit}</span>
              </>
            : <span style={{ color: "#cbd5e1" }}>—</span>
          }
        </div>
        <div style={{ fontSize: 11, color: "#94a3b8", fontFamily: "'Inter',sans-serif", fontWeight: 500, letterSpacing: "0.04em" }}>{label}</div>
      </div>
    </div>
  );
}

// ─── Success Banner ───────────────────────────────────────────────────────────
function SuccessBanner({ show, stats }: { show: boolean; stats: LiveStats | null }) {
  if (!show || !stats) return null;
  const matchRate = stats.total_bank_records > 0
    ? Math.round((stats.matches / stats.total_bank_records) * 100)
    : 0;
  const mt = stats.match_type_counts || {};
  return (
    <div className="anim-bounce-in" style={{
      background: "linear-gradient(135deg,#f0fdf4,#ecfdf5)",
      border: "1.5px solid #bbf7d0", borderRadius: 20,
      padding: "18px 28px", marginBottom: 16,
      display: "flex", alignItems: "center", gap: 16,
      boxShadow: "0 4px 24px rgba(16,185,129,0.08)",
    }}>
      <span style={{ fontSize: 36 }}>🎉</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontWeight: 800, fontSize: 16, color: "#064e3b", marginBottom: 6 }}>
          Reconciliation complete!
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap" }}>
          <span className="retro-text-sm" style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontWeight: 900, fontSize: 28, display: "inline-block" }}>
            {matchRate}%
          </span>
          <span style={{ fontSize: 13, color: "#059669" }}>matched · {stats.total_bank_records} records · {stats.exceptions} exceptions{Object.keys(mt).length > 0 && ( <> · {Object.entries(mt).map(([k,v]) => `${k}: ${v}`).join(", ")}</> )}</span>
        </div>
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        {["⭐","⭐","⭐"].map((s, i) => (
          <span key={i} style={{ fontSize: 22, animation: `pop 0.4s cubic-bezier(0.22,1,0.36,1) ${0.2 + i * 0.15}s both` }}>{s}</span>
        ))}
      </div>
    </div>
  );
}

// ─── Match Table ──────────────────────────────────────────────────────────────
function MatchTable({ complete, rowsData }: { complete: boolean; rowsData: MatchRow[] }) {
  const [filter, setFilter] = useState("All");
  const ref = useRef<HTMLDivElement>(null);
  const v = useInView(ref);
  const rows = filter === "All"
    ? rowsData
    : ["1:N","N:1","N:M"].includes(filter)
      ? rowsData.filter(r => r.matchType === filter)
      : rowsData.filter(r => r.tier === filter);

  return (
    <div ref={ref} className={v ? "anim-slide-up" : ""} style={{ opacity: v ? undefined : 0, animationDelay: "0.1s" }}>
      <div style={{
        background: "#fff", borderRadius: 24,
        border: "1px solid #e2e8f0", overflow: "hidden",
        boxShadow: "0 4px 24px rgba(14,165,233,0.05), 0 1px 2px rgba(0,0,0,0.04)",
      }}>
        <div style={{
          padding: "20px 28px", borderBottom: "1px solid #f1f5f9",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 10, background: "#f0fdf4", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <CheckCircle2 size={15} color="#16a34a" />
            </div>
            <span style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontWeight: 700, fontSize: 15, color: "#0f172a" }}>Matched Pairs</span>
            <span style={{
              padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 600,
              background: "#f0fdf4", color: "#16a34a", border: "1px solid #bbf7d0",
              fontFamily: "'JetBrains Mono',monospace",
            }}>{rowsData.length} records</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <AvatarStack seeds={["Mia","Leo","Zoe","Rex"]} size={28} overlap={9} />
              <span style={{ fontSize: 11, color: "#94a3b8", fontWeight: 500 }}>verified by team</span>
            </div>
          <div style={{ display: "flex", gap: 6 }}>
            {["All", "Tier 1", "Tier 2", "Tier 3", "1:N", "N:1", "N:M"].map(t => (
              <button key={t} onClick={() => setFilter(t)} style={{
                padding: "5px 14px", borderRadius: 20, fontSize: 12, fontWeight: 500,
                cursor: "pointer", fontFamily: "'Inter',sans-serif", transition: "all 0.2s",
                background: filter === t ? "#0f172a" : "transparent",
                color: filter === t ? "#fff" : "#64748b",
                border: `1px solid ${filter === t ? "#0f172a" : "#e2e8f0"}`,
              }}>{t}</button>
            ))}
          </div>
          </div>
        </div>
        <div style={{ overflowX: "auto", overflowY: "auto", maxHeight: 420 }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead style={{ position: "sticky", top: 0, zIndex: 10, background: "#fafafa", boxShadow: "0 1px 2px rgba(0,0,0,0.02)" }}>
              <tr>
                {["ID", "Bank Reference", "Ledger Entry", "Type", "Tier", "LLM", "Confidence", "Date"].map(h => (
                  <th key={h} style={{
                    padding: "10px 16px", textAlign: "left", fontSize: 10,
                    color: "#94a3b8", letterSpacing: "0.08em", fontWeight: 600,
                    fontFamily: "'Inter',sans-serif", borderBottom: "1px solid #f1f5f9",
                  }}>{h.toUpperCase()}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={row.id} style={{
                  borderBottom: "1px solid #f8fafc", cursor: "pointer",
                  transition: "background 0.15s",
                  animation: complete ? `row-in 0.4s cubic-bezier(0.22,1,0.36,1) ${i * 0.06}s both` : "none",
                }}
                  onMouseEnter={e => (e.currentTarget.style.background = "#f8faff")}
                  onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                >
                  <td style={{ padding: "12px 16px", fontFamily: "'JetBrains Mono',monospace", fontSize: 10, color: "#cbd5e1", fontWeight: 600 }}>{row.id}</td>
                  <td style={{ padding: "12px 16px", fontSize: 12, color: "#475569" }}>{row.bank}</td>
                  <td style={{ padding: "12px 16px", fontSize: 12, color: "#475569", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={row.ledger}>{row.ledger}</td>
                  {/* Match Type badge */}
                  <td style={{ padding: "12px 16px" }}>
                    {(() => {
                      const mt = MATCH_TYPE_META[row.matchType] || MATCH_TYPE_META["1:1"];
                      return (
                        <span style={{
                          padding: "3px 9px", borderRadius: 20, fontSize: 11, fontWeight: 700,
                          background: mt.bg, color: mt.color,
                          border: `1px solid ${mt.color}30`,
                          fontFamily: "'JetBrains Mono',monospace",
                        }}>{mt.label}</span>
                      );
                    })()}
                  </td>
                  {/* Tier badge */}
                  <td style={{ padding: "12px 16px" }}>
                    <span style={{
                      padding: "4px 12px", borderRadius: 20, fontSize: 11, fontWeight: 600,
                      background: `${TIER_COLORS[row.tier] || "#94a3b8"}12`,
                      border: `1px solid ${TIER_COLORS[row.tier] || "#94a3b8"}30`,
                      color: TIER_COLORS[row.tier] || "#94a3b8",
                      fontFamily: "'Inter',sans-serif",
                    }}>{row.tier}</span>
                  </td>
                  {/* LLM Source badge */}
                  <td style={{ padding: "12px 16px" }}>
                    {row.llmSource ? (() => {
                      const lm = LLM_SOURCE_META[row.llmSource];
                      return lm ? (
                        <span style={{
                          padding: "3px 9px", borderRadius: 20, fontSize: 10, fontWeight: 600,
                          background: lm.bg, color: lm.color,
                          border: `1px solid ${lm.color}30`,
                          fontFamily: "'Inter',sans-serif",
                        }}>{lm.label}</span>
                      ) : null;
                    })() : <span style={{ color: "#e2e8f0", fontSize: 11 }}>ΓÇö</span>}
                  </td>
                  {/* Confidence bar */}
                  <td style={{ padding: "12px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div style={{ flex: 1, height: 2, background: "#e2e8f0", borderRadius: 2, overflow: "hidden", maxWidth: 64 }}>
                        <div style={{
                          height: "100%",
                          width: `${row.confidence}%`,
                          background: "#0f172a",
                          borderRadius: 2,
                          transition: `width 1s cubic-bezier(0.22,1,0.36,1) ${i * 0.07 + 0.3}s`,
                        }} />
                      </div>
                      <span style={{ fontSize: 11, color: "#0f172a", fontFamily: "'JetBrains Mono',monospace", fontWeight: 700 }}>{row.confidence}%</span>
                    </div>
                  </td>
                  <td style={{ padding: "12px 16px", fontSize: 11, color: "#cbd5e1", fontFamily: "'JetBrains Mono',monospace" }}>{row.date}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── Exceptions ───────────────────────────────────────────────────────────────
function ExceptionsPanel({ complete, excData }: { complete: boolean, excData: ExcRow[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const v = useInView(ref);
  return (
    <div ref={ref} className={v ? "anim-slide-up" : ""} style={{ opacity: v ? undefined : 0, animationDelay: "0.08s" }}>
      <div style={{
        background: "#fff", borderRadius: 24,
        border: "1px solid #e2e8f0", overflow: "hidden", height: "100%",
        boxShadow: "0 4px 24px rgba(14,165,233,0.05), 0 1px 2px rgba(0,0,0,0.04)",
      }}>
        <div style={{
          padding: "20px 28px", borderBottom: "1px solid #f1f5f9",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          background: "#fff",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 32, height: 32, borderRadius: 10, background: "#fef9ee", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <AlertTriangle size={15} color="#f59e0b" />
            </div>
            <span style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontWeight: 700, fontSize: 15, color: "#0f172a" }}>Exceptions</span>
            <span style={{
              padding: "3px 10px", borderRadius: 20, fontSize: 11, fontWeight: 600,
              background: "#f8fafc", color: "#64748b", border: "1px solid #e2e8f0",
              fontFamily: "'JetBrains Mono',monospace",
            }}>{excData.length} items</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <AvatarStack seeds={["Ada","Jay","Nia"]} size={26} overlap={8} />
              <span style={{ fontSize: 11, color: "#94a3b8", fontWeight: 500 }}>reviewing</span>
            </div>
            <button style={{
              padding: "7px 16px", borderRadius: 20,
              background: "transparent", border: "1px solid #e2e8f0",
              color: "#64748b", fontSize: 12, cursor: "pointer",
              display: "flex", alignItems: "center", gap: 5,
              fontFamily: "'Inter',sans-serif", fontWeight: 500,
              transition: "all 0.2s",
            }}
              onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "#f8fafc"; (e.currentTarget as HTMLButtonElement).style.borderColor = "#cbd5e1"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.borderColor = "#e2e8f0"; }}
            ><Download size={12} /> Export</button>
          </div>
        </div>
        <div style={{ overflowY: "auto", maxHeight: 420 }}>
          {excData.map((exc, i) => {
            const meta = CODE_META[exc.code] || DEFAULT_CODE_META;
            return (
              <div key={exc.id} style={{
                padding: "15px 28px", borderBottom: "1px solid #f1f5f9",
                display: "flex", alignItems: "center", gap: 14, cursor: "pointer",
                transition: "background 0.15s",
                animation: complete ? `exc-in 0.4s cubic-bezier(0.22,1,0.36,1) ${i * 0.09}s both` : "none",
              }}
                onMouseEnter={e => (e.currentTarget.style.background = "#f8fafc")}
                onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
              >
                <div style={{
                  width: 34, height: 34, borderRadius: 10, flexShrink: 0,
                  background: "#f1f5f9", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 15,
                }}>{meta.emoji}</div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 12, color: "#0f172a", fontFamily: "'JetBrains Mono',monospace", fontWeight: 600, marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{exc.record}</div>
                  <div style={{ fontSize: 11, color: "#94a3b8" }}>{exc.reason}</div>
                </div>
                <span style={{
                  display: "inline-flex", alignItems: "center", gap: 5,
                  padding: "3px 9px", borderRadius: 6, fontSize: 9, fontWeight: 700,
                  background: meta.bg, border: `1px solid ${meta.dot}22`, color: meta.color,
                  fontFamily: "'JetBrains Mono',monospace", letterSpacing: "0.06em", flexShrink: 0,
                }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: meta.dot, display: "inline-block", flexShrink: 0 }} />
                  {exc.code}
                </span>
                <div style={{ flexShrink: 0 }}>
                  <Avatar seed={AVATAR_SEEDS[i % AVATAR_SEEDS.length]} size={26} border="#e2e8f0" index={i} />
                </div>
                <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 13, color: "#1e293b", fontWeight: 700, flexShrink: 0 }}>{exc.amount}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─── Chart ────────────────────────────────────────────────────────────────────
const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#fff", border: "1px solid #e2e8f0", borderRadius: 12, padding: "10px 16px", boxShadow: "0 8px 24px rgba(0,0,0,0.1)" }}>
      <div style={{ fontSize: 12, color: payload[0].payload.color, fontWeight: 700, fontFamily: "'Plus Jakarta Sans',sans-serif" }}>{payload[0].name}</div>
      <div style={{ fontSize: 16, color: "#0f172a", fontWeight: 800, fontFamily: "'Plus Jakarta Sans',sans-serif" }}>{payload[0].value} records</div>
    </div>
  );
};

function CategoryChart({ chartData }: { chartData: any[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const v = useInView(ref);
  const total = chartData.reduce((s, d) => s + d.value, 0);
  const [active, setActive] = useState<number | null>(null);

  return (
    <div ref={ref} className={v ? "anim-bounce-in" : ""} style={{ opacity: v ? undefined : 0, animationDelay: "0.2s" }}>
      <div style={{
        background: "#fff", borderRadius: 24,
        border: "1px solid #e2e8f0", padding: "28px 24px", height: "100%",
        boxShadow: "0 4px 24px rgba(14,165,233,0.05), 0 1px 2px rgba(0,0,0,0.04)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 22 }}>
          <div style={{ width: 32, height: 32, borderRadius: 10, background: "#f0f9ff", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <BarChart3 size={15} color="#0ea5e9" />
          </div>
          <span style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontWeight: 700, fontSize: 15, color: "#0f172a" }}>Mismatch Types</span>
        </div>
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <div style={{ position: "relative", width: 148, height: 148, flexShrink: 0 }}>
            <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
              <span style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontSize: 26, fontWeight: 900, color: "#0f172a", lineHeight: 1 }}>{total}</span>
              <span style={{ fontSize: 9, color: "#94a3b8", letterSpacing: "0.08em", marginTop: 2, fontWeight: 600 }}>TOTAL</span>
            </div>
            <div style={{ position: "relative", zIndex: 10, width: "100%", height: "100%" }}>
              <ResponsiveContainer width={148} height={148}>
                <PieChart>
                  <Pie data={chartData} cx="50%" cy="50%" innerRadius={44} outerRadius={66}
                    dataKey="value" stroke="none" paddingAngle={2}
                    onMouseEnter={(_, i) => setActive(i)} onMouseLeave={() => setActive(null)}
                    isAnimationActive={v} animationBegin={300} animationDuration={900}
                  >
                    {chartData.map((entry, i) => (
                      <Cell key={i} fill={entry.color}
                        opacity={active === null || active === i ? 1 : 0.3}
                        style={{ transition: "opacity 0.2s", filter: active === i ? `drop-shadow(0 0 6px ${entry.color}80)` : "none", cursor: "pointer" }}
                      />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
          <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
            {chartData.map((d, i) => (
              <div key={d.name} style={{
                display: "flex", alignItems: "center", gap: 10,
                opacity: active === null || active === i ? 1 : 0.35,
                transition: "all 0.2s", transform: active === i ? "translateX(4px)" : "none",
              }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: d.color, flexShrink: 0, boxShadow: active === i ? `0 0 8px ${d.color}` : "none", transition: "box-shadow 0.2s" }} />
                <span style={{ flex: 1, fontSize: 12, color: "#64748b", fontWeight: 500 }}>{d.name}</span>
                <span style={{ fontSize: 12, color: "#0f172a", fontFamily: "'JetBrains Mono',monospace", fontWeight: 700 }}>{d.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Chat ─────────────────────────────────────────────────────────────────────
function TypingDots() {
  return (
    <div style={{ display: "flex", gap: 5, padding: "12px 16px", alignItems: "center" }}>
      {[0, 0.18, 0.36].map((d, i) => (
        <div key={i} style={{ width: 7, height: 7, borderRadius: "50%", background: "#bae6fd", animation: "typing-dot 1.2s ease-in-out infinite", animationDelay: `${d}s` }} />
      ))}
    </div>
  );
}

function QAChat({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [msgs, setMsgs] = useState<ChatMsg[]>([{
    role: "ai", text: "Hi! 👋 I've analyzed your reconciliation run. 5 exceptions need attention — want me to walk you through them?", ts: "09:41",
  }]);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs, typing]);

    const send = async (text?: string) => {
    const msg = (text ?? input).trim(); if (!msg) return;
    const ts = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    setMsgs(m => [...m, { role: "user", text: msg, ts }]);
    setInput(""); setTyping(true);
    
    try {
      const res = await fetch(`${API_BASE}/api/qa`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: msg })
      });
      const data = await res.json();
      setTyping(false);
      setMsgs(m => [...m, { role: "ai", text: data.answer || "Sorry, I couldn't understand that.", ts: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }]);
    } catch (e) {
      setTyping(false);
      setMsgs(m => [...m, { role: "ai", text: "Error connecting to backend.", ts: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) }]);
    }
  };

  return (
    <div style={{
      position: "fixed", top: 0, right: 0, bottom: 0, zIndex: 100,
      width: 390, background: "#fff",
      borderLeft: "1px solid #e2e8f0",
      display: "flex", flexDirection: "column",
      transform: open ? "translateX(0)" : "translateX(100%)",
      transition: "transform 0.4s cubic-bezier(0.22,1,0.36,1)",
      boxShadow: open ? "-24px 0 64px rgba(14,165,233,0.1), -1px 0 0 #e2e8f0" : "none",
    }}>
      {/* Header */}
      <div style={{
        padding: "20px 20px 18px",
        background: "linear-gradient(160deg,#e0f2fe,#ede9fe)",
        borderBottom: "1px solid #e2e8f0",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ position: "relative" }}>
            <Avatar seed="Finley" size={44} border="rgba(255,255,255,0.9)" index={0} />
            <span style={{
              position: "absolute", bottom: 0, right: 0,
              width: 12, height: 12, borderRadius: "50%",
              background: "#22c55e", border: "2px solid #fff",
            }} />
          </div>
          <div>
            <div style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", fontWeight: 800, fontSize: 15, color: "#0f172a" }}>Finley the AI</div>
            <div style={{ fontSize: 11, color: "#0ea5e9", display: "flex", alignItems: "center", gap: 5, fontWeight: 600 }}>
              <span style={{ width: 6, height: 6, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
              Online & ready
            </div>
          </div>
        </div>
        <button onClick={onClose} style={{
          width: 34, height: 34, borderRadius: 10, background: "rgba(255,255,255,0.6)",
          border: "1px solid rgba(255,255,255,0.9)", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          color: "#64748b", transition: "all 0.2s",
        }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "#fef2f2"; (e.currentTarget as HTMLButtonElement).style.color = "#ef4444"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(255,255,255,0.6)"; (e.currentTarget as HTMLButtonElement).style.color = "#64748b"; }}
        ><X size={15} /></button>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 16px 8px" }}>
        {msgs.map((msg, i) => (
          <div key={i} style={{
            marginBottom: 14, display: "flex",
            flexDirection: msg.role === "user" ? "row-reverse" : "row",
            gap: 10, alignItems: "flex-end",
            animation: "chat-in 0.35s cubic-bezier(0.22,1,0.36,1) both",
          }}>
            {msg.role === "ai"
              ? <div style={{ flexShrink: 0 }}><Avatar seed="Finley" size={30} border="#e2e8f0" index={0} /></div>
              : <div style={{ flexShrink: 0 }}><Avatar seed="Sam" size={30} border="#0f172a" index={9} /></div>
            }
            <div style={{ maxWidth: "80%" }}>
              <div style={{
                padding: "12px 16px",
                borderRadius: msg.role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
                background: msg.role === "user" ? "#0f172a" : "#f8fafc",
                border: `1px solid ${msg.role === "user" ? "#0f172a" : "#e2e8f0"}`,
                fontSize: 13, lineHeight: 1.6,
                color: msg.role === "user" ? "#fff" : "#334155",
                fontFamily: "'Inter',sans-serif",
              }}>{msg.text}</div>
              <div style={{ fontSize: 9, color: "#cbd5e1", marginTop: 4, textAlign: msg.role === "user" ? "right" : "left", fontFamily: "'JetBrains Mono',monospace" }}>{msg.ts}</div>
            </div>
          </div>
        ))}
        {typing && (
          <div style={{ display: "flex", gap: 10, alignItems: "flex-end", marginBottom: 14, animation: "chat-in 0.3s ease" }}>
            <div style={{ flexShrink: 0 }}><Avatar seed="Finley" size={30} border="#e2e8f0" index={0} /></div>
            <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: "18px 18px 18px 4px" }}><TypingDots /></div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {/* Suggestions */}
      <div style={{ padding: "0 16px 10px", display: "flex", gap: 6, flexWrap: "wrap" }}>
        {["Show exceptions", "Match rate?", "Explain Tier 3", "Any wins?"].map(s => (
          <button key={s} onClick={() => send(s)} style={{
            padding: "5px 12px", borderRadius: 20, background: "#f8fafc",
            border: "1px solid #e2e8f0", color: "#64748b",
            fontSize: 11, cursor: "pointer", fontFamily: "'Inter',sans-serif",
            transition: "all 0.2s", fontWeight: 500,
          }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "#f0f9ff"; (e.currentTarget as HTMLButtonElement).style.borderColor = "#bae6fd"; (e.currentTarget as HTMLButtonElement).style.color = "#0ea5e9"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "#f8fafc"; (e.currentTarget as HTMLButtonElement).style.borderColor = "#e2e8f0"; (e.currentTarget as HTMLButtonElement).style.color = "#64748b"; }}
          >{s}</button>
        ))}
      </div>

      {/* Input */}
      <div style={{ padding: "10px 16px 24px", borderTop: "1px solid #f1f5f9", display: "flex", gap: 8 }}>
        <input
          value={input} onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && send()}
          placeholder="Ask about your reconciliation…"
          style={{
            flex: 1, padding: "12px 16px", borderRadius: 16,
            background: "#f8fafc", border: "1.5px solid #e2e8f0",
            color: "#0f172a", fontSize: 13, outline: "none",
            fontFamily: "'Inter',sans-serif", transition: "border-color 0.2s, box-shadow 0.2s",
          }}
          onFocus={e => { e.target.style.borderColor = "#38bdf8"; e.target.style.boxShadow = "0 0 0 3px rgba(56,189,248,0.1)"; }}
          onBlur={e => { e.target.style.borderColor = "#e2e8f0"; e.target.style.boxShadow = "none"; }}
        />
        <button onClick={() => send()} style={{
          width: 46, height: 46, borderRadius: 14, background: "#0f172a",
          border: "none", cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0,
          boxShadow: "0 4px 12px rgba(15,23,42,0.2)",
          transition: "all 0.2s",
        }}
          onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1.08)"; (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 6px 20px rgba(15,23,42,0.3)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)"; (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 4px 12px rgba(15,23,42,0.2)"; }}
        ><Send size={16} color="#fff" /></button>
      </div>
    </div>
  );
}

// ─── App ──────────────────────────────────────────────────────────────────────
const API_BASE = (import.meta as any).env?.VITE_API_URL || "http://localhost:8000";

const INIT_METRICS = [
  { label: "MATCH RATE",    value: 0,  unit: "%", icon: TrendingUp, color: "#0ea5e9", bg: "#f0f9ff", delay: 0.05 },
  { label: "TOTAL RECORDS", value: 0,  unit: "",  icon: Target,     color: "#818cf8", bg: "#eef2ff", delay: 0.12 },
  { label: "MATCHED",       value: 0,  unit: "",  icon: Shield,     color: "#f472b6", bg: "#fdf2f8", delay: 0.19 },
  { label: "EXCEPTIONS",    value: 0,  unit: "",  icon: BarChart3,  color: "#34d399", bg: "#ecfdf5", delay: 0.26 },
];

export default function App() {
  const [stages, setStages] = useState<Stage[]>(STAGES.map(s => ({ ...s })));
  const [running, setRunning] = useState(false);
  const [complete, setComplete] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [confetti, setConfetti] = useState(false);
  const [activeTab, setActiveTab] = useState("Dashboard");

  const [matchRows, setMatchRows] = useState<MatchRow[]>([]);
  const [exceptions, setExceptions] = useState<ExcRow[]>([]);
  const [metrics, setMetrics] = useState(INIT_METRICS);
  const [liveStats, setLiveStats] = useState<LiveStats | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);

  // ── helper: build a MatchRow from an SSE "record" event ────────────────────
  const rowFromEvent = (data: any, idx: number): MatchRow => {
    const tierNum = data.tier ?? "1";
    const tierLabel = `Tier ${tierNum}`;
    const lids: string[] = data.ledger_txn_ids || (data.matched_ledger_id ? [data.matched_ledger_id] : ["?"]);
    return {
      id: `M${String(idx).padStart(3, "0")}`,
      bank: data.bank_txn_id || "?",
      ledger: lids.join(", "),
      amount: "—",   // backend doesn't echo amount in stream event
      tier: tierLabel,
      matchType: data.match_type || "1:1",
      confidence: Math.round((data.confidence ?? 0) * 100),
      llmSource: data.llm_source ?? undefined,
      date: "—",
    };
  };

  const runPipeline = useCallback(async (files?: File[]) => {
    if (running) return;
    setRunning(true); setComplete(false); setConfetti(false); setLiveStats(null); setPipelineError(null);
    setStages(STAGES.map(s => ({ ...s, done: false, active: false, count: s.count !== undefined ? 0 : undefined })));
    setMatchRows([]);
    setExceptions([]);
    setMetrics(INIT_METRICS);

    let rowIdx = 0;

    try {
      const options: RequestInit = { method: "POST" };
      if (files && files.length === 2) {
        const formData = new FormData();
        const bankFile = files.find(f => f.name.toLowerCase().includes("bank")) || files[0];
        const ledgerFile = files.find(f => f.name !== bankFile.name) || files[1];
        formData.append("bank_file", bankFile);
        formData.append("ledger_file", ledgerFile);
        options.body = formData;
      } else if (files && files.length === 1) {
        // Single file — send as combined_file (BenchRec format auto-detected by backend)
        const formData = new FormData();
        formData.append("combined_file", files[0]);
        options.body = formData;
      }

      const response = await fetch(`${API_BASE}/reconcile/stream`, options);
      if (!response.ok) {
        const errData = await response.json().catch(() => null);
        setPipelineError(errData?.detail?.message || "Pipeline error");
        setRunning(false);
        return;
      }
      if (!response.body) { setRunning(false); return; }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buf = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() ?? "";

        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;
          const dataStr = part.slice(6).trim();
          if (!dataStr) continue;
          try {
            const data = JSON.parse(dataStr);

            if (data.type === "status") {
              const step: string = data.step || "";
              // Map backend status messages → pipeline stage IDs (strict forward order)
              let activeId = "blocking";
              if      (step.includes("Blocking"))                    activeId = "blocking";
              else if (step.includes("Normaliz") || step.includes("Initializ")) activeId = "normalize";
              else if (step.includes("1:1") || step.includes("Pass 1") || step.includes("Tier")) activeId = "tier1";
              else if (step.includes("1:N")  || step.includes("Pass 2")) activeId = "tier2";
              else if (step.includes("N:1")  || step.includes("Pass 3") ||
                       step.includes("N:M")  || step.includes("Pass 4") ||
                       step.includes("Scoring"))                     activeId = "tier3";

              setStages(prev => {
                const activeIndex = STAGES.findIndex(x => x.id === activeId);
                // Only advance forward — never go backwards
                const currentActiveIdx = prev.findIndex(s => s.active);
                const currentDoneCount = prev.filter(s => s.done).length;
                if (activeIndex < Math.max(currentActiveIdx, currentDoneCount)) return prev;
                return prev.map(s => {
                  const myIndex = STAGES.findIndex(x => x.id === s.id);
                  return { ...s, active: s.id === activeId, done: myIndex < activeIndex };
                });
              });
            }

            else if (data.type === "counts") {
              // bank + ledger counts — could show in UI
            }

            else if (data.type === "record") {
              // ΓöÇΓöÇ Live match row ΓöÇΓöÇ
              const row = rowFromEvent(data, rowIdx++);
              setMatchRows(prev => [...prev, row]);

              // advance stage counts
              setStages(prev => prev.map(s => {
                if (s.id === "tier1" && data.tier === "1")  return { ...s, count: (s.count ?? 0) + 1 };
                if (s.id === "tier2" && data.tier === "2")  return { ...s, count: (s.count ?? 0) + 1 };
                if (s.id === "tier3" && data.tier === "3")  return { ...s, count: (s.count ?? 0) + 1 };
                return s;
              }));
            }

            else if (data.type === "progress") {
              // Progress events only update live counts shown in the UI —
              // stage active/done is exclusively controlled by status events
              // to prevent the avatar from jumping backwards.
            }

            else if (data.type === "complete") {
              const st: LiveStats = data.stats;
              setLiveStats(st);
              setMetrics([
                { label: "MATCH RATE",    value: Math.round((st.matches / Math.max(1, st.total_bank_records)) * 100), unit: "%", icon: TrendingUp, color: "#0ea5e9", bg: "#f0f9ff", delay: 0.05 },
                { label: "TOTAL RECORDS", value: st.total_bank_records, unit: "", icon: Target,    color: "#818cf8", bg: "#eef2ff", delay: 0.12 },
                { label: "MATCHED",       value: st.matches,            unit: "", icon: Shield,    color: "#f472b6", bg: "#fdf2f8", delay: 0.19 },
                { label: "EXCEPTIONS",    value: st.exceptions,         unit: "", icon: BarChart3, color: "#34d399", bg: "#ecfdf5", delay: 0.26 },
              ]);

              // populate exceptions from the complete payload
              if (data.exceptions) {
                const excRows: ExcRow[] = (data.exceptions as any[]).map((e: any, i: number) => ({
                  id: `E${String(i).padStart(3, "0")}`,
                  record: e.bank_txn_id || "?",
                  amount: "—",
                  reason: e.detail || e.reason_code || "Pipeline exception",
                  code: e.reason_code || "UNKNOWN_EXCEPTION",
                }));
                setExceptions(excRows);
              }

              setStages(prev => prev.map(s => ({ ...s, active: false, done: true })));
              setRunning(false);
              setComplete(true);
              setConfetti(true);
            }

            else if (data.type === "error") {
              console.error("[SSE error]", data.message);
              setRunning(false);
            }
          } catch (e) {
            console.error("[SSE parse]", e);
          }
        }
      }
    } catch (e) {
      console.error("[fetch]", e);
      setRunning(false);
    }
  }, [running]);

  return (
    <div style={{ minHeight: "100vh", background: "#f0f7ff" }}>
      <Confetti active={confetti} />

      {/* Main Navigation */}
      <TopNav onChat={() => setChatOpen(true)} activeTab={activeTab} onChangeTab={setActiveTab} />

      {/* Conditionally render Hero only on Dashboard */}
      {activeTab === "Dashboard" && (
        <>
          <Hero onRun={runPipeline} running={running} liveStats={liveStats} />
          <WaveDivider />
        </>
      )}

      {/* White content */}
      <main style={{ padding: "24px 40px 64px", maxWidth: 1440, margin: "0 auto", minHeight: "50vh" }}>
        {activeTab === "Dashboard" ? (
          <>
            {pipelineError && (
              <div className="anim-bounce-in" style={{
                background: "#fef2f2", border: "1.5px solid #fecaca", borderRadius: 20,
                padding: "16px 24px", marginBottom: 16, display: "flex", alignItems: "center", gap: 12,
                color: "#991b1b", fontFamily: "'Inter',sans-serif", fontSize: 14, fontWeight: 500
              }}>
                <AlertTriangle size={18} /> {pipelineError}
              </div>
            )}
            <SuccessBanner show={complete} stats={liveStats} />
            <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: 16, marginBottom: 16 }}>
              <UploadZone onRun={runPipeline} running={running} />
              <PipelineProgress stages={stages} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 16, marginBottom: 16 }}>
              {metrics.map(m => <MetricCard key={m.label} {...m} active={complete} />)}
            </div>
            <div style={{ marginBottom: 16 }}>
              <MatchTable complete={complete} rowsData={matchRows} />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: 16 }}>
              <ExceptionsPanel complete={complete} excData={exceptions} />
              <CategoryChart chartData={liveStats ? [
                { name: "Matched (1:1)",  value: liveStats.match_type_counts?.["1:1"] ?? 0,  color: "#0ea5e9" },
                { name: "Matched (1:N)",  value: liveStats.match_type_counts?.["1:N"] ?? 0,  color: "#818cf8" },
                { name: "Matched (N:1)",  value: liveStats.match_type_counts?.["N:1"] ?? 0,  color: "#f472b6" },
                { name: "Matched (N:M)",  value: liveStats.match_type_counts?.["N:M"] ?? 0,  color: "#f59e0b" },
                { name: "Exceptions",     value: liveStats.exceptions,                        color: "#ef4444" },
              ].filter(d => d.value > 0) : []} />
            </div>
          </>
        ) : (
          <div className="anim-fade-in" style={{
            display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
            padding: "80px 20px", textAlign: "center", color: "#64748b", fontFamily: "'Inter',sans-serif"
          }}>
            <h2 style={{ fontSize: 24, fontWeight: 700, color: "#0f172a", marginBottom: 12 }}>{activeTab} is Coming Soon</h2>
            <p style={{ fontSize: 15, maxWidth: 400, lineHeight: 1.6 }}>
              This page hasn't been built yet. The prototype focuses exclusively on the core reconciliation flow in the Dashboard.
            </p>
          </div>
        )}

        {/* Floating chat button */}
        {!chatOpen && (
          <button onClick={() => setChatOpen(true)} style={{
            position: "fixed", bottom: 28, right: 28,
            width: 56, height: 56, borderRadius: "50%",
            background: "#0f172a",
            border: "none", cursor: "pointer",
            display: "flex", alignItems: "center", justifyContent: "center",
            boxShadow: "0 8px 28px rgba(15,23,42,0.25)",
            transition: "all 0.25s cubic-bezier(0.22,1,0.36,1)",
            zIndex: 50,
          }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1.1)"; (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 12px 36px rgba(15,23,42,0.35)"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)"; (e.currentTarget as HTMLButtonElement).style.boxShadow = "0 8px 28px rgba(15,23,42,0.25)"; }}
          >
            <Sparkles size={22} color="#fff" />
          </button>
        )}
      </main>

      <QAChat open={chatOpen} onClose={() => setChatOpen(false)} />
    </div>
  );
}
