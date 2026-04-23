import { useEffect, useMemo, useState } from 'react';

import './AgentActivityFeed.css';

const AGENT_STEPS = [
  {
    key: 'concierge',
    title: '🧑‍💼 Concierge',
    runningText: 'parsing request...',
  },
  {
    key: 'head_chef',
    title: '👨‍🍳 Head Chef',
    runningText: 'creating menu...',
  },
  {
    key: 'accountant',
    title: '💰 Accountant',
    runningText: 'checking budget...',
  },
  {
    key: 'logistics',
    title: '🚚 Logistics Lead',
    runningText: 'planning...',
  },
  {
    key: 'stock_manager',
    title: '📦 Stock Manager',
    runningText: 'checking stock...',
  },
];

function formatSeconds(seconds) {
  if (seconds == null) {
    return '';
  }
  return `${seconds.toFixed(2)}s`;
}

export default function AgentActivityFeed({
  isRunning,
  lastProcessingTimeSeconds,
  negotiationRoundsUsed,
}) {
  const [activeIndex, setActiveIndex] = useState(-1);
  const [showNegotiation, setShowNegotiation] = useState(false);
  const [negotiationRound, setNegotiationRound] = useState(0);

  const steps = useMemo(() => AGENT_STEPS, []);

  useEffect(() => {
    if (!isRunning) {
      setActiveIndex(-1);
      setShowNegotiation(false);
      setNegotiationRound(0);
      return undefined;
    }

    setActiveIndex(0);
    setShowNegotiation(false);
    setNegotiationRound(0);

    const stepIntervalMs = 550;
    const negotiationStartIndex = 2;

    const intervalId = window.setInterval(() => {
      setActiveIndex((prev) => {
        const next = prev + 1;

        if (next === negotiationStartIndex) {
          setShowNegotiation(true);
          setNegotiationRound(1);
          window.setTimeout(() => setNegotiationRound(2), stepIntervalMs);
          window.setTimeout(() => setNegotiationRound(3), stepIntervalMs * 2);
        }

        if (next >= steps.length) {
          window.clearInterval(intervalId);
          return steps.length - 1;
        }

        return next;
      });
    }, stepIntervalMs);

    return () => window.clearInterval(intervalId);
  }, [isRunning, steps.length]);

  useEffect(() => {
    if (isRunning) {
      return;
    }
    if (negotiationRoundsUsed && negotiationRoundsUsed > 0) {
      setShowNegotiation(true);
      setNegotiationRound(Math.min(3, negotiationRoundsUsed));
    } else {
      setShowNegotiation(false);
      setNegotiationRound(0);
    }
  }, [isRunning, negotiationRoundsUsed]);

  return (
    <div className="activityFeed">
      <ol className="stepList">
        {steps.map((step, idx) => {
          const isCompletedRun = !isRunning && lastProcessingTimeSeconds != null;
          const isDone = isCompletedRun ? true : idx < activeIndex;
          const isActive = isRunning && idx === activeIndex;
          const isPending = !isDone && !isActive;

          return (
            <li key={step.key} className="stepRow">
              <div className="stepTitle">{step.title}</div>
              <div className="stepStatus">
                {isDone && <span className="statusDone">✅ Done</span>}
                {isActive && <span className="statusRunning">{step.runningText}</span>}
                {isPending && <span className="statusPending">waiting...</span>}
              </div>
            </li>
          );
        })}
      </ol>

      {showNegotiation && (
        <div className="negotiationBox">
          <div className="negotiationTitle">⚡ Budget conflict detected — negotiating...</div>
          <div className="negotiationRounds">Round {negotiationRound} of 3...</div>
        </div>
      )}

      {lastProcessingTimeSeconds != null && !isRunning && (
        <div className="processingTime">Processing time: {formatSeconds(lastProcessingTimeSeconds)}</div>
      )}
    </div>
  );
}
