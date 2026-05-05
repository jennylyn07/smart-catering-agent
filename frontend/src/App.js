import './App.css';
import { useState, useEffect, useRef } from 'react';
import AgentActivityFeed from './components/AgentActivityFeed';
import OrderForm from './components/OrderForm';
import ResultsDashboard from './components/ResultsDashboard';

function App() {
  const [isLoading, setIsLoading] = useState(false);
  const [finalPlan, setFinalPlan] = useState(null);
  const [processingTimeSeconds, setProcessingTimeSeconds] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [negotiationRoundsUsed, setNegotiationRoundsUsed] = useState(null);
  const [showHistory, setShowHistory] = useState(false);
  const [historyOrders, setHistoryOrders] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [agentStatuses, setAgentStatuses] = useState({});
  const sseRef = useRef(null);

  // Clean up SSE on unmount
  useEffect(() => {
    return () => { if (sseRef.current) sseRef.current.close(); };
  }, []);

  function connectSSE(sessionId, apiKey) {
    if (sseRef.current) sseRef.current.close();
    setAgentStatuses({});

    // SSE via fetch polyfill since EventSource doesn't support headers
    // Use polling approach instead
    let cancelled = false;

    async function poll() {
      while (!cancelled) {
        try {
          const r = await fetch(
            `/api/v1/catering/progress/${sessionId}`,
            {
              headers: { 'X-API-Key': apiKey },
              signal: AbortSignal.timeout(180000),
            }
          );
          const text = await r.text();
          const lines = text.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const evt = JSON.parse(line.slice(6));
                if (evt.type === 'agent_update') {
                  setAgentStatuses(prev => ({
                    ...prev,
                    [evt.agent]: evt.status,
                  }));
                  if (evt.agent === 'accountant' && evt.status === 'done') {
                    // Could be negotiating
                  }
                } else if (evt.type === 'done' || evt.type === 'timeout') {
                  cancelled = true;
                  break;
                }
              } catch {}
            }
          }
          break;
        } catch {
          break;
        }
      }
    }
    poll();
    sseRef.current = { close: () => { cancelled = true; } };
  }

  async function handleOrderSubmit(payload) {
    setIsLoading(true);
    setFinalPlan(null);
    setProcessingTimeSeconds(null);
    setNegotiationRoundsUsed(null);
    setErrorMessage(null);
    setAgentStatuses({});
    setShowHistory(false);

    const apiKey = process.env.REACT_APP_API_KEY;
    if (!apiKey) {
      setIsLoading(false);
      setErrorMessage('Missing REACT_APP_API_KEY.');
      return;
    }

    try {
      const parts = [];
      if (payload.guest_count) parts.push(`${payload.guest_count} guests`);
      if (payload.cuisine_preferences?.length)
        parts.push(`${payload.cuisine_preferences.join(' and ')} cuisine`);
      if (payload.budget_php) parts.push(`PHP ${payload.budget_php} budget`);
      if (payload.event_date) parts.push(payload.event_date);
      if (payload.event_name) parts.push(payload.event_name);
      if (payload.location) parts.push(`at ${payload.location}`);
      if (payload.dietary_restrictions?.length)
        parts.push(`dietary requirements: ${payload.dietary_restrictions.join(', ')}`);
      if (payload.allergies?.length)
        parts.push(`allergies: ${payload.allergies.join(', ')}`);
      if (payload.notes) parts.push(payload.notes);

      const raw_customer_text = parts.join(', ');

      const response = await fetch('/api/v1/catering/order', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': apiKey,
        },
        body: JSON.stringify({ raw_customer_text }),
      });

      const body = await response.json().catch(() => null);

      if (!response.ok) {
        const detail = body?.error || body?.detail || body?.message;
        throw new Error(detail || `Request failed (${response.status})`);
      }

      // Connect SSE if session_id available
      const sessionId = body?._session_id;
      if (sessionId) connectSSE(sessionId, apiKey);

      const messageType = body?.header?.message_type;
      if (messageType === 'final_plan') {
        const plan = body?.payload;
        setFinalPlan(plan);
        setProcessingTimeSeconds(plan?.total_processing_time_seconds ?? null);
        setNegotiationRoundsUsed(plan?.negotiation_rounds_used ?? 0);
        // Mark all agents done on completion
        setAgentStatuses({
          concierge: 'done', head_chef: 'done', accountant: 'done',
          logistics: 'done', stock_manager: 'done',
        });

        // Refresh history in background so it's ready 
        // when user clicks History
        const apiKey2 = process.env.REACT_APP_API_KEY;
        fetch('/api/v1/catering/orders', {
          headers: { 'X-API-Key': apiKey2 },
        })
          .then(r => r.json())
          .then(body => setHistoryOrders(body.orders || []))
          .catch(() => {});
      } else if (messageType === 'error') {
        throw new Error(body?.payload?.message || 'Server error.');
      } else {
        throw new Error('Unexpected server response.');
      }
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }

  async function handleShowHistory() {
    setShowHistory(true);
    setSelectedOrder(null);
    setHistoryLoading(true);
    const apiKey = process.env.REACT_APP_API_KEY;
    try {
      const response = await fetch('/api/v1/catering/orders', {
        headers: { 'X-API-Key': apiKey },
      });
      const body = await response.json();
      setHistoryOrders(body.orders || []);
    } catch {
      setHistoryOrders([]);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function handleSelectOrder(order) {
    if (selectedOrder?.order_id === order.order_id) {
      setSelectedOrder(null);
      return;
    }
    const apiKey = process.env.REACT_APP_API_KEY;
    try {
      const r = await fetch(
        `/api/v1/catering/order/${order.order_id}`,
        { headers: { 'X-API-Key': apiKey } }
      );
      const body = await r.json();
      if (body?.payload) {
        setSelectedOrder({ ...order, fullPlan: body.payload });
      } else {
        setSelectedOrder(order);
      }
    } catch {
      setSelectedOrder(order);
    }
  }

  function handleNewOrder() {
    setShowHistory(false);
    setSelectedOrder(null);
    setErrorMessage(null);
  }

  return (
    <div className="container">
      <div className="appHeader">
        <h1 className="brandTitle">
          Smart Catering <span>System</span>
        </h1>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <button
            onClick={handleShowHistory}
            style={{
              background: 'none',
              border: '1px solid var(--neu-border, #B5BFC6)',
              borderRadius: '999px',
              padding: '6px 16px',
              cursor: 'pointer',
              fontSize: '13px',
              fontWeight: '600',
              color: 'var(--neu-dark, #6E7F8D)',
            }}
          >
            📋 History
          </button>
          {showHistory && (
            <button
              onClick={handleNewOrder}
              style={{
                background: 'var(--color-accent)',
                border: 'none',
                borderRadius: '999px',
                padding: '6px 16px',
                cursor: 'pointer',
                fontSize: '13px',
                fontWeight: '600',
                color: 'white',
              }}
            >
              + New Order
            </button>
          )}
        </div>
      </div>

      {errorMessage && (
        <div className="errorBanner" role="alert">
          {typeof errorMessage === 'string'
            ? errorMessage
            : JSON.stringify(errorMessage)}
        </div>
      )}

      {showHistory ? (
        <section className="resultsSection" aria-label="Order History">
          <div style={{
            background: 'var(--neu-bg)',
            borderRadius: 'var(--radius-md)',
            boxShadow: 'var(--shadow-neu-out-lg)',
            padding: '24px',
          }}>
            <h2 style={{
              fontFamily: 'Syne, sans-serif',
              marginBottom: '16px',
            }}>📋 Order History</h2>
            {historyLoading && (
              <p style={{ color: 'var(--neu-ink-muted)' }}>
                Loading past orders...
              </p>
            )}
            {!historyLoading && historyOrders.length === 0 && (
              <p style={{ color: 'var(--neu-ink-muted)' }}>
                No past orders found.
              </p>
            )}
            {!historyLoading && historyOrders.length > 0 && (
              <table style={{
                width: '100%', borderCollapse: 'collapse',
                fontSize: '14px',
              }}>
                <thead>
                  <tr style={{ background: 'var(--neu-mid)' }}>
                    {['Event','Date','Guests','Budget',
                      'Total Cost','Status'].map(h => (
                      <th key={h} style={{
                        padding: '10px 14px', textAlign: 'left',
                        fontSize: '11px', letterSpacing: '0.8px',
                        textTransform: 'uppercase',
                        color: 'var(--neu-ink-muted)',
                        fontWeight: '700',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {historyOrders.map((order, i) => (
                    <>
                      <tr
                        key={i}
                        onClick={() => handleSelectOrder(order)}
                        style={{
                          borderBottom: '1px solid var(--neu-mid)',
                          cursor: 'pointer',
                          background: selectedOrder?.order_id === order.order_id
                            ? 'rgba(232,96,28,0.05)' : 'transparent',
                        }}
                      >
                        <td style={{ padding: '12px 14px', fontWeight: '600' }}>
                          {order.event_name}
                        </td>
                        <td style={{ padding: '12px 14px',
                          color: 'var(--neu-ink-muted)' }}>
                          {order.event_date
                            ? new Date(order.event_date).toLocaleDateString(
                                'en-PH', {
                                  month: 'short', day: 'numeric',
                                  year: 'numeric'
                                })
                            : '—'}
                        </td>
                        <td style={{ padding: '12px 14px' }}>
                          {order.guest_count}
                        </td>
                        <td style={{ padding: '12px 14px' }}>
                          ₱{Number(order.budget_php).toLocaleString()}
                        </td>
                        <td style={{ padding: '12px 14px' }}>
                          ₱{Number(order.total_cost_php).toLocaleString()}
                        </td>
                        <td style={{ padding: '12px 14px' }}>
                          <span style={{
                            color: order.within_budget
                              ? 'var(--color-ok)' : 'var(--color-warn)',
                            fontWeight: '700', fontSize: '12px',
                          }}>
                            {order.within_budget
                              ? '✓ Within budget' : '✗ Over budget'}
                          </span>
                        </td>
                      </tr>
                      {selectedOrder?.order_id === order.order_id && (
                        <tr key={`${i}-detail`}>
                          <td colSpan={6} style={{ padding: '0' }}>
                            {selectedOrder.fullPlan ? (
                              <div style={{ padding: '16px' }}>
                                <ResultsDashboard
                                  finalPlan={selectedOrder.fullPlan}
                                />
                              </div>
                            ) : (
                              <div style={{
                                padding: '16px 20px',
                                color: 'var(--neu-ink-muted)',
                                fontSize: '13px',
                              }}>
                                Loading full plan...
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      ) : (
        <div className="sideByGrid">
          <div className="leftCol">
            <section className="panel" aria-label="Order Form">
              <h2>Order Form</h2>
              <OrderForm
                isLoading={isLoading}
                onSubmit={handleOrderSubmit}
              />
            </section>
            <section className="panel" style={{ marginTop: '16px' }}
              aria-label="Agent Activity Feed">
              <h2>Agent Activity Feed</h2>
              <AgentActivityFeed
                isRunning={isLoading}
                lastProcessingTimeSeconds={processingTimeSeconds}
                negotiationRoundsUsed={negotiationRoundsUsed}
                agentStatuses={agentStatuses}
              />
            </section>
          </div>
          <div className="rightCol">
            {finalPlan ? (
              <ResultsDashboard finalPlan={finalPlan} />
            ) : (
              <div style={{
                background: 'var(--neu-bg)',
                borderRadius: 'var(--radius-md)',
                boxShadow: 'var(--shadow-neu-in)',
                padding: '48px 32px',
                textAlign: 'center',
                color: 'var(--neu-ink-muted)',
                fontSize: '14px',
                minHeight: '300px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexDirection: 'column',
                gap: '12px',
              }}>
                <div style={{ fontSize: '32px' }}>🍽️</div>
                <div style={{ fontWeight: '600' }}>
                  Your catering plan will appear here
                </div>
                <div>Fill out the form and click Generate</div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
