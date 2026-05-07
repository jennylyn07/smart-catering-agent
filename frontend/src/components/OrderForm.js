import { useState } from 'react';

import './OrderForm.css';

const CUISINE_OPTIONS = [
  { key: 'filipino', label: 'Filipino' },
  { key: 'chinese', label: 'Chinese' },
  { key: 'western', label: 'Western' },
  { key: 'international', label: 'International' },
];

const ALLERGY_OPTIONS = [
  { key: 'nuts', label: 'Nuts' },
  { key: 'dairy', label: 'Dairy' },
  { key: 'gluten', label: 'Gluten' },
  { key: 'seafood', label: 'Seafood' },
];

const DIETARY_OPTIONS = [
  { key: 'vegetarian', label: 'Vegetarian' },
  { key: 'halal', label: 'Halal' },
  { key: 'vegan', label: 'Vegan' },
];

function toggleSetValue(setter) {
  return (key) =>
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
}

export default function OrderForm({ isLoading, onSubmit }) {
  const [eventName, setEventName] = useState('');
  const [eventDate, setEventDate] = useState('');
  const [eventTime, setEventTime] = useState('18:00');
  const [location, setLocation] = useState('');
  const [guestCount, setGuestCount] = useState(50);
  const [budgetPhp, setBudgetPhp] = useState(45000);
  const [cuisinePreferences, setCuisinePreferences] = useState(new Set());
  const [allergies, setAllergies] = useState(new Set());
  const [dietaryRestrictions, setDietaryRestrictions] = useState(new Set());
  const [specialNotes, setSpecialNotes] = useState('');

  const toggleCuisine = toggleSetValue(setCuisinePreferences);
  const toggleAllergy = toggleSetValue(setAllergies);
  const toggleDietary = toggleSetValue(setDietaryRestrictions);

  function handleSubmit(e) {
    e.preventDefault();

    const payload = {
      event_name: eventName,
      event_date: eventDate,
      event_time: eventTime,
      location,
      guest_count: Number(guestCount),
      budget_php: Number(budgetPhp),
      cuisine_preferences: Array.from(cuisinePreferences),
      allergies: Array.from(allergies),
      dietary_restrictions: Array.from(dietaryRestrictions),
      notes: specialNotes,
    };

    if (onSubmit) {
      onSubmit(payload);
    }
  }

  return (
    <form className="orderForm" onSubmit={handleSubmit}>
      <div className="formGrid">
        {/* Row 1: Event Name — full width */}
        <label className="field span2">
          <span className="labelText">Event Name</span>
          <input
            type="text"
            value={eventName}
            onChange={(e) => setEventName(e.target.value)}
            placeholder="e.g., Company Anniversary Dinner"
            disabled={isLoading}
            required
          />
        </label>

        {/* Row 2: Date | Time — side by side */}
        <label className="field">
          <span className="labelText">Event Date</span>
          <input
            type="date"
            value={eventDate}
            onChange={(e) => setEventDate(e.target.value)}
            min={new Date().toISOString().split('T')[0]}
            disabled={isLoading}
            required
          />
        </label>

        <label className="field">
          <span className="labelText">Event Time</span>
          <input
            type="time"
            value={eventTime}
            onChange={(e) => setEventTime(e.target.value)}
            disabled={isLoading}
            required
          />
        </label>

        {/* Row 3: Location — full width */}
        <label className="field span2">
          <span className="labelText">Location</span>
          <input
            type="text"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            placeholder="e.g., Quezon City"
            disabled={isLoading}
            required
          />
        </label>

        {/* Row 4: Guests | Budget — side by side */}
        <label className="field">
          <span className="labelText">Number of Guests</span>
          <input
            type="number"
            min="1"
            step="1"
            value={guestCount}
            onChange={(e) => setGuestCount(e.target.value)}
            disabled={isLoading}
            required
          />
        </label>

        <label className="field">
          <span className="labelText">Budget in PHP</span>
          <input
            type="number"
            min="0"
            step="1"
            value={budgetPhp}
            onChange={(e) => setBudgetPhp(e.target.value)}
            disabled={isLoading}
            required
          />
        </label>
      </div>

      <fieldset className="group" disabled={isLoading}>
        <legend>Cuisine Preferences</legend>
        <div className="checkGrid">
          {CUISINE_OPTIONS.map((opt) => (
            <label key={opt.key} className="check">
              <input
                type="checkbox"
                checked={cuisinePreferences.has(opt.key)}
                onChange={() => toggleCuisine(opt.key)}
              />
              <span>{opt.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="group" disabled={isLoading}>
        <legend>Allergies</legend>
        <div className="checkGrid">
          {ALLERGY_OPTIONS.map((opt) => (
            <label key={opt.key} className="check">
              <input
                type="checkbox"
                checked={allergies.has(opt.key)}
                onChange={() => toggleAllergy(opt.key)}
              />
              <span>{opt.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className="group" disabled={isLoading}>
        <legend>Dietary Restrictions</legend>
        <div className="checkGrid">
          {DIETARY_OPTIONS.map((opt) => (
            <label key={opt.key} className="check">
              <input
                type="checkbox"
                checked={dietaryRestrictions.has(opt.key)}
                onChange={() => toggleDietary(opt.key)}
              />
              <span>{opt.label}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="field">
        <span className="labelText">Special Notes</span>
        <textarea
          value={specialNotes}
          onChange={(e) => setSpecialNotes(e.target.value)}
          placeholder="Any special instructions or notes..."
          rows={4}
          disabled={isLoading}
        />
      </label>

      <button className="primaryButton" type="submit" disabled={isLoading}>
        {isLoading ? 'Generating…' : 'Generate Catering Plan'}
      </button>
    </form>
  );
}
