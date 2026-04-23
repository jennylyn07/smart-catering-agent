import './App.css';

import { useState } from 'react';

import AgentActivityFeed from './components/AgentActivityFeed';
import OrderForm from './components/OrderForm';
import ResultsDashboard from './components/ResultsDashboard';

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [finalPlan, setFinalPlan] = useState(null);
  const [processingTimeSeconds, setProcessingTimeSeconds] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [negotiationRoundsUsed, setNegotiationRoundsUsed] = useState(null);

  async function handleOrderSubmit(payload) {
    setIsLoading(true);
    setFinalPlan(null);
    setProcessingTimeSeconds(null);
    setNegotiationRoundsUsed(null);
    setErrorMessage(null);

    const apiKey = process.env.REACT_APP_API_KEY;
    if (!apiKey) {
      setIsLoading(false);
      setErrorMessage(
        'Missing REACT_APP_API_KEY. Add it to frontend/.env and restart the frontend dev server.'
      );
      return;
    }

    try {
      const response = await fetch('/api/v1/catering/order', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': apiKey,
        },
        body: JSON.stringify(payload),
      });

      const body = await response.json().catch(() => null);

      if (!response.ok) {
        const detail = body?.error || body?.detail || body?.message;
        throw new Error(detail || `Request failed (${response.status})`);
      }

      const messageType = body?.header?.message_type;
      if (messageType === 'final_plan') {
        const plan = body?.payload;
        setFinalPlan(plan);
        setProcessingTimeSeconds(plan?.total_processing_time_seconds ?? null);
        setNegotiationRoundsUsed(plan?.negotiation_rounds_used ?? 0);
      } else if (messageType === 'error') {
        const msg = body?.payload?.message || 'The server returned an error.';
        throw new Error(msg);
      } else {
        throw new Error('Unexpected server response.');
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="container">
      <div className="appHeader">
        <h1 className="brandTitle">
          Smart Catering <span>System</span>
        </h1>
        <div>
          Frontend UI
        </div>
      </div>

      {errorMessage && (
        <div className="errorBanner" role="alert">
          {errorMessage}
        </div>
      )}

      <div className="panelGrid">
        <section className="panel" aria-label="Order Form">
          <h2>Order Form</h2>
          <OrderForm isLoading={isLoading} onSubmit={handleOrderSubmit} />
        </section>

        <section className="panel" aria-label="Agent Activity Feed">
          <h2>Agent Activity Feed</h2>
          <AgentActivityFeed
            isRunning={isLoading}
            lastProcessingTimeSeconds={processingTimeSeconds}
            negotiationRoundsUsed={negotiationRoundsUsed}
          />
        </section>
      </div>

      {finalPlan && (
        <section className="resultsSection" aria-label="Results">
          <ResultsDashboard finalPlan={finalPlan} />
        </section>
      )}
    </div>
  );
}

export default App;
