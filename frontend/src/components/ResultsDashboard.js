import { useMemo, useState } from 'react';

import './ResultsDashboard.css';

function formatPhp(amount) {
  if (amount == null || Number.isNaN(amount)) {
    return '-';
  }
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
          <tr>
            {columns.map((c) => (
              <th key={c.key}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx}>
              {columns.map((c) => (
                <td key={c.key}>{row[c.key]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ResultsDashboard({ finalPlan }) {
  const [activeTab, setActiveTab] = useState('menu');

  const summary = useMemo(() => {
    const cost = finalPlan?.cost_report;
    const event = finalPlan?.event_specification;

    const totalCost = cost?.total_cost_php;
    const budget = cost?.budget_php;

    const withinBudget = cost?.within_budget ?? cost?.is_within_budget;

    return {
      guestCount: event?.guest_count,
      totalCost,
      budget,
      withinBudget,
    };
  }, [finalPlan]);

  const menuRows = useMemo(() => {
    const items = finalPlan?.menu_plan?.menu_items || [];
    return items.map((d) => ({
      dish: d.name,
      servings: d.servings,
      notes: d.category || '-',
    }));
  }, [finalPlan]);

  const costRows = useMemo(() => {
    const items = finalPlan?.cost_report?.cost_per_dish || [];
    return items.map((d) => ({
      dish: d.dish_name,
      cost_php: `₱${formatPhp(d.cost_php)}`,
    }));
  }, [finalPlan]);

  const timelineRows = useMemo(() => {
    const items = finalPlan?.logistics_plan?.timeline || [];
    return items.map((t) => ({
      time: t.time,
      task: t.description,
      owner: t.owner,
    }));
  }, [finalPlan]);

  const procurementRows = useMemo(() => {
    const items = finalPlan?.procurement_list?.items_to_purchase || [];
    return items.map((p) => ({
      ingredient: p.ingredient,
      quantity: `${p.quantity} ${p.unit}`,
      supplier: p.suggested_supplier || '-',
      est_cost_php: `₱${formatPhp(p.estimated_cost_php)}`,
    }));
  }, [finalPlan]);

  if (!finalPlan) {
    return null;
  }

  const budgetBadgeText = summary.withinBudget ? 'Within budget' : 'Over budget';
  const budgetBadgeClass = summary.withinBudget ? 'badgeOk' : 'badgeWarn';

  return (
    <div className="resultsCard">
      <div className="summaryRow">
        <div className="summaryItem">
          <div className="summaryLabel">Guest count</div>
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
        <div className={`badge ${budgetBadgeClass}`}>{budgetBadgeText}</div>
      </div>

      <div className="tabRow" role="tablist" aria-label="Results tabs">
        <button
          className={activeTab === 'menu' ? 'tab tabActive' : 'tab'}
          onClick={() => setActiveTab('menu')}
          type="button"
          role="tab"
          aria-selected={activeTab === 'menu'}
        >
          Menu
        </button>
        <button
          className={activeTab === 'cost' ? 'tab tabActive' : 'tab'}
          onClick={() => setActiveTab('cost')}
          type="button"
          role="tab"
          aria-selected={activeTab === 'cost'}
        >
          Cost breakdown
        </button>
        <button
          className={activeTab === 'timeline' ? 'tab tabActive' : 'tab'}
          onClick={() => setActiveTab('timeline')}
          type="button"
          role="tab"
          aria-selected={activeTab === 'timeline'}
        >
          Timeline
        </button>
        <button
          className={activeTab === 'procurement' ? 'tab tabActive' : 'tab'}
          onClick={() => setActiveTab('procurement')}
          type="button"
          role="tab"
          aria-selected={activeTab === 'procurement'}
        >
          Procurement
        </button>
      </div>

      {activeTab === 'menu' && (
        <SafeTable
          columns={[
            { key: 'dish', label: 'Dish' },
            { key: 'servings', label: 'Servings' },
            { key: 'notes', label: 'Notes' },
          ]}
          rows={menuRows}
          emptyText="No menu items."
        />
      )}

      {activeTab === 'cost' && (
        <SafeTable
          columns={[
            { key: 'dish', label: 'Dish' },
            { key: 'cost_php', label: 'Cost' },
          ]}
          rows={costRows}
          emptyText="No cost items."
        />
      )}

      {activeTab === 'timeline' && (
        <SafeTable
          columns={[
            { key: 'time', label: 'Start time' },
            { key: 'task', label: 'Task' },
            { key: 'owner', label: 'Owner' },
          ]}
          rows={timelineRows}
          emptyText="No timeline entries."
        />
      )}

      {activeTab === 'procurement' && (
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
      )}
    </div>
  );
}
