import { useState, useEffect } from 'react';
import './AdaptPanel.css';

const CHANGE_TYPES = [
  { key: 'guest_count_change',  label: '👥 Guest Count',  group: 'people' },
  { key: 'budget_change',       label: '💰 Budget',        group: 'people' },
  { key: 'dietary_addition',    label: '🥗 Add Dietary',   group: 'people' },
  { key: 'allergy_addition',    label: '⚠️ Add Allergy',   group: 'people' },
  { key: 'date_change',         label: '📅 Event Date',    group: 'logistics' },
  { key: 'event_time_change',   label: '🕒 Event Time',    group: 'logistics' },
  { key: 'location_change',     label: '📍 Location',      group: 'logistics' },
  { key: 'notes_change',        label: '📝 Notes',         group: 'logistics' },
];

const DIETARY_OPTIONS  = ['Vegetarian', 'Vegan', 'Halal', 'Gluten-Free'];

// Which agents re-run per change type (shown as hint to user)
const AGENT_HINT = {
  guest_count_change: 'Re-runs: Head Chef → Accountant → Logistics → Stock',
  budget_change:      'Re-runs: Accountant → Logistics → Stock',
  dietary_addition:   'Re-runs: Head Chef → Accountant → Logistics → Stock',
  allergy_addition:   'Re-runs: Head Chef → Accountant → Logistics → Stock',
  date_change:        'Re-runs: Logistics → Stock only (fast)',
  event_time_change:  'Re-runs: Logistics → Stock only (fast)',
  location_change:    'Re-runs: Logistics → Stock only (fast)',
  notes_change:       'Re-runs: Logistics → Stock only (fast)',
};

export default function AdaptPanel({ finalPlan, isAdapting, adaptMessage, onAdapt }) {
  const spec = finalPlan?.event_specification || {};

  const [collapsed, setCollapsed]       = useState(true);
  const [selectedType, setSelectedType] = useState('guest_count_change');
  const [guestValue, setGuestValue]     = useState(spec.guest_count ?? 50);
  const [budgetValue, setBudgetValue]   = useState(spec.budget_php ?? '');
  const [dateValue, setDateValue]       = useState(spec.event_date ?? '');
  const [timeValue, setTimeValue]       = useState(spec.event_time ?? '18:00');
  const [locationValue, setLocationValue] = useState(spec.location ?? '');
  const [notesValue, setNotesValue]     = useState(spec.notes ?? '');
  const [dietaryValue, setDietaryValue] = useState('Vegetarian');
  const [allergyValue, setAllergyValue] = useState('');

  // Sync inputs when plan updates after successful adapt
  useEffect(() => {
    setGuestValue(spec.guest_count ?? 50);
    setBudgetValue(spec.budget_php ?? '');
    setDateValue(spec.event_date ?? '');
    setTimeValue(spec.event_time ?? '18:00');
    setLocationValue(spec.location ?? '');
    setNotesValue(spec.notes ?? '');
  }, [finalPlan]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleApply() {
    if (isAdapting) return;
    switch (selectedType) {
      case 'guest_count_change': {
        const v = parseInt(guestValue, 10);
        if (!v || v < 1) return;
        onAdapt(selectedType, v);
        break;
      }
      case 'budget_change': {
        const v = parseFloat(budgetValue);
        if (isNaN(v) || v < 0) return;
        onAdapt(selectedType, v);
        break;
      }
      case 'dietary_addition':
        onAdapt(selectedType, dietaryValue);
        break;
      case 'allergy_addition': {
        const v = allergyValue.trim();
        if (!v) return;
        onAdapt(selectedType, v);
        break;
      }
      case 'date_change': {
        if (!dateValue) return;
        onAdapt(selectedType, dateValue);
        break;
      }
      case 'event_time_change': {
        if (!timeValue) return;
        onAdapt(selectedType, timeValue);
        break;
      }
      case 'location_change': {
        const v = locationValue.trim();
        if (!v) return;
        onAdapt(selectedType, v);
        break;
      }
      case 'notes_change':
        onAdapt(selectedType, notesValue);
        break;
      default:
        break;
    }
  }

  const currentDietary  = spec.dietary_restrictions || [];
  const currentAllergies = spec.allergies || [];
  const availableDietary = DIETARY_OPTIONS.filter(d => !currentDietary.includes(d));

  return (
    <div className={`adaptPanel${collapsed ? ' collapsed' : ''}`}>
      <button
        className="adaptHeader"
        onClick={() => setCollapsed(c => !c)}
        aria-expanded={!collapsed}
        id="adapt-panel-toggle"
      >
        <span className="adaptTitle">✏️ Modify This Plan</span>
        <span className={`adaptChevron${collapsed ? '' : ' open'}`}>›</span>
      </button>

      {!collapsed && (
        <div className="adaptBody">
          {/* Feedback banner */}
          {adaptMessage && (
            <div className={`adaptFeedback ${adaptMessage.type}`} role="alert">
              {adaptMessage.type === 'success' ? '✅ ' : '⚠️ '}
              {adaptMessage.text}
            </div>
          )}

          {/* Current spec summary */}
          <div className="adaptSpecSummary">
            <span>Guests: <strong>{spec.guest_count}</strong></span>
            {spec.budget_php != null && (
              <span>Budget: <strong>₱{Number(spec.budget_php).toLocaleString()}</strong></span>
            )}
            {spec.event_date && <span>Date: <strong>{spec.event_date}</strong></span>}
            {spec.event_time && <span>Time: <strong>{spec.event_time}</strong></span>}
            {spec.location   && <span>Location: <strong>{spec.location}</strong></span>}
            {currentDietary.length > 0 && (
              <span>Dietary: <strong>{currentDietary.join(', ')}</strong></span>
            )}
            {currentAllergies.length > 0 && (
              <span>Allergies: <strong>{currentAllergies.join(', ')}</strong></span>
            )}
          </div>

          {/* Group labels + pills */}
          <div className="pillGroups">
            <div className="pillGroup">
              <span className="pillGroupLabel">People &amp; Cost</span>
              <div className="changeTypePills">
                {CHANGE_TYPES.filter(c => c.group === 'people').map(ct => (
                  <button
                    key={ct.key}
                    className={`pill${selectedType === ct.key ? ' active' : ''}`}
                    onClick={() => setSelectedType(ct.key)}
                    id={`adapt-type-${ct.key}`}
                    disabled={
                      (ct.key === 'dietary_addition' && availableDietary.length === 0)
                    }
                  >
                    {ct.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="pillGroup">
              <span className="pillGroupLabel">Logistics</span>
              <div className="changeTypePills">
                {CHANGE_TYPES.filter(c => c.group === 'logistics').map(ct => (
                  <button
                    key={ct.key}
                    className={`pill${selectedType === ct.key ? ' active' : ''}`}
                    onClick={() => setSelectedType(ct.key)}
                    id={`adapt-type-${ct.key}`}
                  >
                    {ct.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Agent hint */}
          <p className="agentHint">{AGENT_HINT[selectedType]}</p>

          {/* Input area */}
          <div className="adaptInputArea">
            {selectedType === 'guest_count_change' && (
              <div className="adaptInputGroup">
                <label htmlFor="adapt-guest-count" className="adaptLabel">New guest count</label>
                <input id="adapt-guest-count" type="number" min="1" className="adaptInput"
                  value={guestValue} onChange={e => setGuestValue(e.target.value)} disabled={isAdapting} />
              </div>
            )}
            {selectedType === 'budget_change' && (
              <div className="adaptInputGroup">
                <label htmlFor="adapt-budget" className="adaptLabel">New budget (PHP)</label>
                <input id="adapt-budget" type="number" min="0" step="500" className="adaptInput"
                  value={budgetValue} onChange={e => setBudgetValue(e.target.value)}
                  disabled={isAdapting} placeholder="e.g. 80000" />
              </div>
            )}
            {selectedType === 'dietary_addition' && (
              <div className="adaptInputGroup">
                <label htmlFor="adapt-dietary" className="adaptLabel">Add dietary requirement</label>
                {availableDietary.length === 0
                  ? <p className="adaptHint">All supported dietary requirements are already applied.</p>
                  : <select id="adapt-dietary" className="adaptInput adaptSelect"
                      value={dietaryValue} onChange={e => setDietaryValue(e.target.value)} disabled={isAdapting}>
                      {availableDietary.map(d => <option key={d} value={d}>{d}</option>)}
                    </select>}
              </div>
            )}
            {selectedType === 'allergy_addition' && (
              <div className="adaptInputGroup">
                <label htmlFor="adapt-allergy" className="adaptLabel">Add allergen to exclude</label>
                <input id="adapt-allergy" type="text" className="adaptInput"
                  value={allergyValue} onChange={e => setAllergyValue(e.target.value)}
                  disabled={isAdapting} placeholder="e.g. Peanuts, Shellfish, Dairy" />
                {currentAllergies.length > 0 && (
                  <p className="adaptHint">Currently excluded: {currentAllergies.join(', ')}</p>
                )}
              </div>
            )}
            {selectedType === 'date_change' && (
              <div className="adaptInputGroup">
                <label htmlFor="adapt-date" className="adaptLabel">New event date</label>
                <input id="adapt-date" type="date" className="adaptInput"
                  value={dateValue} onChange={e => setDateValue(e.target.value)} disabled={isAdapting} />
                <p className="adaptHint">Only Logistics &amp; Stock re-run — timeline and procurement urgency recalculate.</p>
              </div>
            )}
            {selectedType === 'event_time_change' && (
              <div className="adaptInputGroup">
                <label htmlFor="adapt-time" className="adaptLabel">New event start time</label>
                <input id="adapt-time" type="time" className="adaptInput"
                  value={timeValue} onChange={e => setTimeValue(e.target.value)} disabled={isAdapting} />
              </div>
            )}
            {selectedType === 'location_change' && (
              <div className="adaptInputGroup">
                <label htmlFor="adapt-location" className="adaptLabel">New venue / location</label>
                <input id="adapt-location" type="text" className="adaptInput"
                  value={locationValue} onChange={e => setLocationValue(e.target.value)}
                  disabled={isAdapting} placeholder="e.g. BGC, Taguig" />
                <p className="adaptHint">Delivery routes and logistics timeline regenerate for the new venue.</p>
              </div>
            )}
            {selectedType === 'notes_change' && (
              <div className="adaptInputGroup">
                <label htmlFor="adapt-notes" className="adaptLabel">Special notes / requirements</label>
                <textarea id="adapt-notes" className="adaptInput adaptTextarea" rows={3}
                  value={notesValue} onChange={e => setNotesValue(e.target.value)}
                  disabled={isAdapting} placeholder="e.g. Early morning setup, outdoor venue, live cooking stations" />
                <p className="adaptHint">Logistics Lead re-runs and interprets notes to adjust timeline tasks.</p>
              </div>
            )}

            <button
              className={`applyBtn${isAdapting ? ' loading' : ''}`}
              onClick={handleApply}
              disabled={isAdapting || (selectedType === 'dietary_addition' && availableDietary.length === 0)}
              id="adapt-apply-btn"
            >
              {isAdapting
                ? <><span className="adaptSpinner" aria-hidden="true" />Updating plan…</>
                : 'Apply Changes'}
            </button>
          </div>

          <p className="adaptDisclaimer">
            Only impacted agents re-run. Results update in-place — plan is not wiped on error.
          </p>
        </div>
      )}
    </div>
  );
}
