import { useEffect, useMemo, useRef, useState } from 'react';
import './AgentActivityFeed.css';

const AGENT_STEPS = [
  { key: 'concierge',     title: '🧑‍💼 Concierge',      runningText: 'parsing request…',    durationMs: 8000  },
  { key: 'head_chef',     title: '👨‍🍳 Head Chef',       runningText: 'creating menu…',      durationMs: 35000 },
  { key: 'accountant',    title: '💰 Accountant',        runningText: 'checking budget…',    durationMs: 30000 },
  { key: 'logistics',     title: '🚚 Logistics Lead',    runningText: 'planning timeline…',  durationMs: 25000 },
  { key: 'stock_manager', title: '📦 Stock Manager',     runningText: 'checking stock…',     durationMs: 25000 },
];

// After this many ms into the Accountant's active phase, show negotiation indicator
const ACCOUNTANT_NEGOTIATE_AFTER_MS = 12000;

// Cumulative start times derived from durations
const CUMULATIVE_MS = AGENT_STEPS.reduce((acc, step, i) => {
  acc.push(i === 0 ? 0 : acc[i - 1] + AGENT_STEPS[i - 1].durationMs);
  return acc;
}, []);

function formatSeconds(s) {
  if (s == null) return '';
  return `${s.toFixed(1)}s`;
}

export default function AgentActivityFeed({
  isRunning,
  lastProcessingTimeSeconds,
  negotiationRoundsUsed,
  agentStatuses = {},
}) {
  const [elapsedMs, setElapsedMs]         = useState(0);
  const [showNegotiation, setShowNegotiation] = useState(false);
  const [negotiationRound, setNegotiationRound] = useState(0);
  const startTimeRef = useRef(null);
  const rafRef       = useRef(null);

  // Live elapsed-time ticker
  useEffect(() => {
    if (!isRunning) {
      setElapsedMs(0);
      startTimeRef.current = null;
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }
    startTimeRef.current = Date.now();
    const tick = () => {
      setElapsedMs(Date.now() - startTimeRef.current);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [isRunning]);

  // Negotiation display
  useEffect(() => {
    if (!isRunning) {
      if (negotiationRoundsUsed && negotiationRoundsUsed > 0) {
        setShowNegotiation(true);
        setNegotiationRound(Math.min(3, negotiationRoundsUsed));
      } else {
        setShowNegotiation(false);
        setNegotiationRound(0);
      }
      return;
    }
    setShowNegotiation(false);
    setNegotiationRound(0);
  }, [isRunning, negotiationRoundsUsed]);

  const hasRealStatuses = Object.keys(agentStatuses).length > 0;
  const isCompleted     = !isRunning && lastProcessingTimeSeconds != null;

  const stepStates = useMemo(() => {
    const accountantIdx   = AGENT_STEPS.findIndex(s => s.key === 'accountant');
    const accountantStart = CUMULATIVE_MS[accountantIdx];

    return AGENT_STEPS.map((step, idx) => {
      // --- Post-completion: use SSE-derived statuses ---
      if (isCompleted) {
        const done = hasRealStatuses ? agentStatuses[step.key] === 'done' : true;
        // Show negotiation on accountant if rounds were used
        const negotiating = step.key === 'accountant' && !done &&
          negotiationRoundsUsed && negotiationRoundsUsed > 0;
        return { isDone: done, isActive: false, isPending: !done, isNegotiating: negotiating };
      }

      // --- During loading: time-based simulation ---
      if (isRunning) {
        const stepStart = CUMULATIVE_MS[idx];
        const stepEnd   = stepStart + step.durationMs;
        if (elapsedMs >= stepEnd)   return { isDone: true,  isActive: false, isPending: false, isNegotiating: false };
        if (elapsedMs >= stepStart) {
          // Accountant: after initial budget-check phase, show negotiation
          const isNegotiating = step.key === 'accountant' &&
            elapsedMs >= accountantStart + ACCOUNTANT_NEGOTIATE_AFTER_MS;
          return { isDone: false, isActive: true, isPending: false, isNegotiating };
        }
        return { isDone: false, isActive: false, isPending: true, isNegotiating: false };
      }

      return { isDone: false, isActive: false, isPending: true, isNegotiating: false };
    });
  }, [isRunning, isCompleted, hasRealStatuses, agentStatuses, elapsedMs, negotiationRoundsUsed]);

  const elapsedSec = elapsedMs / 1000;

  return (
    <div className="activityFeed">

      {/* Live elapsed time banner */}
      {isRunning && (
        <div style={{
          background: 'var(--neu-bg)',
          boxShadow: 'var(--shadow-neu-in)',
          borderRadius: '999px',
          padding: '6px 16px',
          marginBottom: '12px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '13px',
          fontWeight: '700',
          color: 'var(--color-accent)',
        }}>
          <span style={{ animation: 'spin 1.2s linear infinite', display: 'inline-block' }}>⚙️</span>
          Multi-agent pipeline running… {elapsedSec.toFixed(0)}s
        </div>
      )}

      <ol className="stepList">
        {AGENT_STEPS.map((step, idx) => {
          const { isDone, isActive, isPending, isNegotiating } = stepStates[idx];
          const isParallelGroup = idx === 3 || idx === 4;
          return (
            <li key={step.key} className={`stepRow${isNegotiating ? ' stepNegotiating' : ''}`}>
              <div className="stepTitle">
                {step.title}
                {isParallelGroup && isActive && (
                  <span style={{ fontSize: '10px', color: 'var(--neu-ink-muted)', marginLeft: 4 }}>∥ parallel</span>
                )}
              </div>
              <div className="stepStatus">
                {isDone    && <span className="statusDone">✅ Done</span>}
                {isActive  && !isNegotiating && <span className="statusRunning">{step.runningText}</span>}
                {isNegotiating && (
                  <span className="statusNegotiating">⚡ negotiating with Chef…</span>
                )}
                {isPending && <span className="statusPending">waiting…</span>}
              </div>
            </li>
          );
        })}
      </ol>

      {showNegotiation && (
        <div className="negotiationBox">
          <div className="negotiationTitle">⚡ Budget conflict detected — negotiated</div>
          <div className="negotiationRounds">Round {negotiationRound} of 3</div>
        </div>
      )}

      {isCompleted && (
        <div className="processingTime">
          ✓ Completed in {formatSeconds(lastProcessingTimeSeconds)}
        </div>
      )}
    </div>
  );
}
