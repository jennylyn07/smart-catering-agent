import { useMemo, useState } from 'react';
import './ResultsDashboard.css';

function formatPhp(amount) {
  if (amount == null || Number.isNaN(amount)) return '-';
  return amount.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

function SafeTable({ columns, rows, emptyText }) {
  if (!rows || rows.length === 0) {
    return <div className="emptyState">{emptyText}</div>;
  }
  return (
    <div className="tableWrap">
      <table className="table">
        <thead>
          <tr>{columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx}>
              {columns.map((c) => <td key={c.key}>{row[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const AGENT_STEPS = [
  { key: 'concierge', label: '🧑‍💼 Concierge' },
  { key: 'head_chef', label: '👨‍🍳 Head Chef' },
  { key: 'accountant', label: '💰 Accountant' },
  { key: 'logistics', label: '🚚 Logistics' },
  { key: 'stock', label: '📦 Stock Manager' },
];

function AgentPipeline() {
  return (
    <div className="agentPipeline">
      {AGENT_STEPS.map((step, idx) => (
        <div className="agentStep" key={step.key}>
          <div className="agentChip">
            <span className="check">✓</span>
            {step.label}
          </div>
          {idx < AGENT_STEPS.length - 1 && (
            <span className="agentArrow">→</span>
          )}
        </div>
      ))}
    </div>
  );
}

function DietaryPills({ dietary, allergies }) {
  const pills = [];

  const colorMap = {
    halal: 'pillHalal',
    vegan: 'pillVegan',
    vegetarian: 'pillVegetarian',
    no_meat: 'pillVegetarian',
    no_dairy: 'pillDiet',
    no_eggs: 'pillDiet',
  };

  (dietary || []).forEach((d) => {
    pills.push({ label: d.replace(/_/g, ' '), cls: colorMap[d] || 'pillDiet' });
  });

  (allergies || []).forEach((a) => {
    pills.push({ label: `⚠ ${a} allergy`, cls: 'pillAllergen' });
  });

  if (pills.length === 0) return null;

  return (
    <div className="pillRow">
      {pills.map((p, i) => (
        <span key={i} className={`pill ${p.cls}`}>{p.label}</span>
      ))}
    </div>
  );
}

export default function ResultsDashboard({ finalPlan }) {
  const [activeTab, setActiveTab] = useState('menu');
  const [chefExpanded, setChefExpanded] = useState(true);

  const summary = useMemo(() => {
    const cost = finalPlan?.cost_report;
    const event = finalPlan?.event_specification;
    return {
      guestCount: event?.guest_count,
      totalCost: cost?.total_cost_php,
      budget: cost?.budget_php,
      withinBudget: cost?.within_budget ?? cost?.is_within_budget,
      processingTime: finalPlan?.total_processing_time_seconds,
      negotiationRounds: finalPlan?.negotiation_rounds_used ?? 0,
      recommendedPrice: cost?.recommended_selling_price_php ?? null,
      marginPct: cost?.estimated_margin_percent ?? null,
    };
  }, [finalPlan]);

  const dietary = finalPlan?.event_specification?.dietary_restrictions || [];
  const allergies = finalPlan?.event_specification?.allergies || [];

  const menuItems = useMemo(
    () => finalPlan?.menu_plan?.menu_items || [],
    [finalPlan]
  );
  const chefRationale = finalPlan?.menu_plan?.rationale || '';

  const menuRows = useMemo(() =>
    menuItems.map((d) => ({
      dish: d.name,
      servings: d.servings,
      category: d.category || '-',
      kcal:    d.nutrition?.calories   != null ? `${d.nutrition.calories} kcal`    : '-',
      protein: d.nutrition?.protein_g  != null ? `${d.nutrition.protein_g}g`       : '-',
      carbs:   d.nutrition?.carbs_g    != null ? `${d.nutrition.carbs_g}g`         : '-',
      fat:     d.nutrition?.fat_g      != null ? `${d.nutrition.fat_g}g`           : '-',
    })), [menuItems]);

  const costRows = useMemo(() => {
    const items = finalPlan?.cost_report?.cost_per_dish || [];
    return items.map((d) => ({
      dish: d.dish_name,
      cost_php: `₱${formatPhp(d.cost_php)}`,
    }));
  }, [finalPlan]);

  const flaggedItems = finalPlan?.cost_report?.flagged_items || [];
  const costNotes = finalPlan?.cost_report?.notes || '';
  const suggestedBudget = finalPlan?.cost_report?.suggested_budget_php || null;

  const staffingNotes = finalPlan?.logistics_plan?.staffing_notes || '';

  const timelineRows = useMemo(() => {
    const items = finalPlan?.logistics_plan?.timeline || [];
    return items.map((t) => ({
      time: t.time ? new Date(t.time).toLocaleString('en-PH', {
        month: 'short', day: 'numeric', year: 'numeric',
        hour: 'numeric', minute: '2-digit', hour12: true
      }) : '-',
      task: t.description,
      owner: t.owner,
    }));
  }, [finalPlan]);

  const procurementRows = useMemo(() => {
    const items = finalPlan?.procurement_list?.items_to_purchase || [];
    return items.map((p) => ({
      ingredient: p.ingredient,
      quantity: `${typeof p.quantity === 'number'
        ? p.quantity % 1 === 0
          ? p.quantity
          : parseFloat(p.quantity.toFixed(2))
        : p.quantity} ${p.unit}`,
      supplier: p.suggested_supplier || '-',
      est_cost_php: `₱${formatPhp(p.estimated_cost_php)}`,
    }));
  }, [finalPlan]);

  const wasteRiskItems = finalPlan?.procurement_list?.waste_risk_items || [];
  const wasteNotes = finalPlan?.procurement_list?.waste_minimization_notes || '';

  if (!finalPlan) return null;

  const budgetBadgeText = summary.withinBudget ? '✓ Within budget' : '✗ Over budget';
  const budgetBadgeClass = summary.withinBudget ? 'badgeOk' : 'badgeWarn';

  return (
    <div className="resultsCard">

      {/* Summary row */}
      <div className="summaryRow">
        <div className="summaryItem">
          <div className="summaryLabel">Guests</div>
          <div className="summaryValue">{summary.guestCount ?? '-'}</div>
        </div>
        <div className="summaryItem">
          <div className="summaryLabel">Total cost</div>
          <div className="summaryValue">₱{formatPhp(summary.totalCost)}</div>
        </div>
        <div className="summaryItem">
          <div className="summaryLabel">Budget</div>
          <div className="summaryValue">₱{formatPhp(summary.budget)}</div>
        </div>
        <div className="summaryItem">
          <div className="summaryLabel">Processing time</div>
          <div className="summaryValue">
            {summary.processingTime != null
              ? `${Number(summary.processingTime).toFixed(1)}s` 
              : '-'}
          </div>
        </div>
        <div className={`badge ${budgetBadgeClass}`}>{budgetBadgeText}</div>
      </div>

      {/* Dietary and allergy pills */}
      <DietaryPills dietary={dietary} allergies={allergies} />

      {/* Agent pipeline */}
      <AgentPipeline />

      {/* Tabs */}
      <div className="tabRow" role="tablist">
        {[
          { key: 'menu', label: '👨‍🍳 Menu' },
          { key: 'cost', label: '💰 Cost' },
          { key: 'timeline', label: '🚚 Timeline' },
          { key: 'procurement', label: '📦 Procurement' },
        ].map((t) => (
          <button
            key={t.key}
            className={activeTab === t.key ? 'tab tabActive' : 'tab'}
            onClick={() => setActiveTab(t.key)}
            type="button"
            role="tab"
            aria-selected={activeTab === t.key}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Menu tab */}
      {activeTab === 'menu' && (
        <div className="tabPanel">
          {menuItems.length > 0 && menuItems.length < 5 && (
            <div className="warningBanner">
              ⚠ Only {menuItems.length} dish{menuItems.length === 1 ? '' : 'es'} 
              selected — dietary or allergy constraints may have limited the menu.
            </div>
          )}
          {chefRationale && (
            <div className="infoCard">
              <div
                className="infoCardTitle"
                style={{ cursor: 'pointer' }}
                onClick={() => setChefExpanded(!chefExpanded)}
              >
                <span className="icon">👨‍🍳</span>
                Head Chef Reasoning
                <span style={{ marginLeft: 'auto', fontSize: '12px' }}>
                  {chefExpanded ? '▲ collapse' : '▼ expand'}
                </span>
              </div>
              {chefExpanded && (
                <div className="infoCardBody">{chefRationale}</div>
              )}
            </div>
          )}
          <SafeTable
            columns={[
              { key: 'dish',     label: 'Dish' },
              { key: 'servings', label: 'Servings' },
              { key: 'category', label: 'Category' },
              { key: 'kcal',    label: 'Calories' },
              { key: 'protein', label: 'Protein' },
              { key: 'carbs',   label: 'Carbs' },
              { key: 'fat',     label: 'Fat' },
            ]}
            rows={menuRows}
            emptyText="No menu items."
          />
        </div>
      )}

      {/* Cost tab */}
      {activeTab === 'cost' && (
        <div className="tabPanel">
          {/* Profitability card */}
          {summary.recommendedPrice != null && (
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '12px',
              marginBottom: '4px',
            }}>
              <div className="summaryItem">
                <div className="summaryLabel">Recommended Selling Price</div>
                <div className="summaryValue" style={{ fontSize: '16px', color: 'var(--color-ok)' }}>
                  ₱{formatPhp(summary.recommendedPrice)}
                </div>
              </div>
              <div className="summaryItem">
                <div className="summaryLabel">Est. Profit Margin</div>
                <div className="summaryValue" style={{ fontSize: '16px', color: 'var(--color-ok)' }}>
                  {summary.marginPct != null ? `${summary.marginPct.toFixed(0)}%` : '-'}
                </div>
              </div>
            </div>
          )}
          <div className="negotiationPanel">
            <div className="negotiationTitle">
              💰 Accountant — Budget Review
            </div>
            {summary.negotiationRounds > 0 ? (
              <>
                <div className="negotiationRounds">
                  {summary.negotiationRounds}
                </div>
                <div className="negotiationSub">
                  negotiation round{summary.negotiationRounds === 1
                    ? '' : 's'} between Accountant and Head Chef
                </div>
                {flaggedItems.length > 0 && (
                  <>
                    <div className="summaryLabel"
                      style={{ marginBottom: 8 }}>
                      {summary.withinBudget 
                        ? 'Resolved after negotiation' 
                        : 'Could not be resolved within budget'}
                    </div>
                    <div className="flaggedList">
                      {flaggedItems.map((item, i) => (
                        <span key={i} className="flaggedItem"
                          style={{ 
                            color: summary.withinBudget 
                              ? 'var(--color-ok)' 
                              : 'var(--color-warn)' 
                          }}>
                          {item}
                        </span>
                      ))}
                    </div>
                  </>
                )}
                {costNotes && (
                  <div className="negotiationNotes">{costNotes}</div>
                )}
                {suggestedBudget && (
                  <div style={{
                    marginTop: '12px',
                    padding: '10px 14px',
                    background: 'var(--neu-bg)',
                    boxShadow: 'var(--shadow-neu-out)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '13px',
                    fontWeight: '600',
                    color: 'var(--blue)',
                  }}>
                    💡 Suggested realistic budget: ₱{Number(suggestedBudget).toLocaleString()}
                  </div>
                )}
              </>
            ) : (
              <>
                <div className="negotiationRounds"
                  style={{ color: 'var(--color-ok)', fontSize: 18,
                    fontWeight: 700, marginBottom: 4 }}>
                  ✓ Budget approved — no negotiation required
                </div>
                {costNotes && (
                  <div className="negotiationNotes">{costNotes}</div>
                )}
              </>
            )}
          </div>
          <SafeTable
            columns={[
              { key: 'dish', label: 'Dish' },
              { key: 'cost_php', label: 'Ingredient cost' },
            ]}
            rows={costRows}
            emptyText="No cost items."
          />
        </div>
      )}

      {/* Timeline tab */}
      {activeTab === 'timeline' && (
        <div className="tabPanel">
          {staffingNotes && (
            <div className="infoCard">
              <div className="infoCardTitle">
                <span className="icon">👥</span>
                Staffing Plan — Logistics Lead
              </div>
              <div className="infoCardBody">{staffingNotes}</div>
            </div>
          )}
          <SafeTable
            columns={[
              { key: 'time', label: 'Start time' },
              { key: 'task', label: 'Task' },
              { key: 'owner', label: 'Owner' },
            ]}
            rows={timelineRows}
            emptyText="No timeline entries."
          />
        </div>
      )}

      {/* Procurement tab */}
      {activeTab === 'procurement' && (
        <div className="tabPanel">
          {wasteRiskItems.length > 0 && (
            <div className="infoCard">
              <div className="infoCardTitle">
                <span className="icon">⚠</span>
                Waste Risk Items — Stock Manager
              </div>
              <div className="infoCardBody">
                <div className="flaggedList" style={{ marginBottom: 12 }}>
                  {wasteRiskItems.map((item, i) => (
                    <span key={i} className="flaggedItem" 
                      style={{ color: '#b7770d' }}>
                      {item}
                    </span>
                  ))}
                </div>
                {wasteNotes && (
                  <div style={{ fontSize: 13, lineHeight: 1.7 }}>
                    {wasteNotes}
                  </div>
                )}
              </div>
            </div>
          )}
          <SafeTable
            columns={[
              { key: 'ingredient', label: 'Ingredient' },
              { key: 'quantity', label: 'Quantity' },
              { key: 'supplier', label: 'Supplier' },
              { key: 'est_cost_php', label: 'Est. cost' },
            ]}
            rows={procurementRows}
            emptyText="No procurement items."
          />
          {!wasteRiskItems.length && wasteNotes && (
            <div className="infoCard">
              <div className="infoCardTitle">
                <span className="icon">📦</span>
                Waste Minimization — Stock Manager
              </div>
              <div className="infoCardBody">{wasteNotes}</div>
            </div>
          )}
        </div>
      )}

    </div>
  );
}
