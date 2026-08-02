import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { MOBILITY_NEEDS, WEEKDAYS } from "./constants";
import { useCreateRecurringSeriesMutation, useCreateTripMutation } from "./useTrips";

export function BookingForm() {
  const navigate = useNavigate();
  const createTrip = useCreateTripMutation();
  const createSeries = useCreateRecurringSeriesMutation();

  const [pickupAddress, setPickupAddress] = useState("");
  const [dropoffAddress, setDropoffAddress] = useState("");
  const [mobilityNeed, setMobilityNeed] = useState("");
  const [notes, setNotes] = useState("");
  const [isRecurring, setIsRecurring] = useState(false);

  const [pickupDateTime, setPickupDateTime] = useState("");

  const [startDate, setStartDate] = useState("");
  const [pickupTime, setPickupTime] = useState("");
  const [endDate, setEndDate] = useState("");
  const [weekdays, setWeekdays] = useState<number[]>([]);

  const [error, setError] = useState<string | null>(null);

  function toggleWeekday(value: number) {
    setWeekdays((prev) =>
      prev.includes(value) ? prev.filter((day) => day !== value) : [...prev, value],
    );
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      if (isRecurring) {
        await createSeries.mutateAsync({
          pickup_address: pickupAddress,
          dropoff_address: dropoffAddress,
          pickup_time: `${pickupTime}:00`,
          weekdays,
          start_date: startDate,
          end_date: endDate || null,
          mobility_need: mobilityNeed,
          notes,
        });
      } else {
        // datetime-local values are timezone-naive; convert to an explicit
        // UTC instant so the backend's 24h-cutoff comparison is unambiguous.
        await createTrip.mutateAsync({
          scheduled_pickup_time: new Date(pickupDateTime).toISOString(),
          pickup_address: pickupAddress,
          dropoff_address: dropoffAddress,
          mobility_need: mobilityNeed,
          notes,
        });
      }
      navigate("/rider", { replace: true });
    } catch {
      setError("Could not book this trip. Check the addresses and try again.");
    }
  }

  const isSubmitting = createTrip.isPending || createSeries.isPending;

  return (
    <div className="portal-page">
      <h1>Book a trip</h1>
      <form onSubmit={handleSubmit} className="auth-form">
        <label htmlFor="pickup_address">Pickup address</label>
        <input
          id="pickup_address"
          value={pickupAddress}
          onChange={(e) => setPickupAddress(e.target.value)}
          required
        />

        <label htmlFor="dropoff_address">Dropoff address</label>
        <input
          id="dropoff_address"
          value={dropoffAddress}
          onChange={(e) => setDropoffAddress(e.target.value)}
          required
        />

        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={isRecurring}
            onChange={(e) => setIsRecurring(e.target.checked)}
          />
          Repeat weekly
        </label>

        {!isRecurring && (
          <>
            <label htmlFor="pickup_datetime">Pickup date &amp; time</label>
            <input
              id="pickup_datetime"
              type="datetime-local"
              value={pickupDateTime}
              onChange={(e) => setPickupDateTime(e.target.value)}
              required
            />
          </>
        )}

        {isRecurring && (
          <>
            <label htmlFor="start_date">Start date</label>
            <input
              id="start_date"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              required
            />

            <label htmlFor="pickup_time">Pickup time</label>
            <input
              id="pickup_time"
              type="time"
              value={pickupTime}
              onChange={(e) => setPickupTime(e.target.value)}
              required
            />

            <span>Repeat on</span>
            <div className="weekday-picker">
              {WEEKDAYS.map((day) => (
                <label key={day.value} className="weekday-picker__option">
                  <input
                    type="checkbox"
                    checked={weekdays.includes(day.value)}
                    onChange={() => toggleWeekday(day.value)}
                  />
                  {day.label}
                </label>
              ))}
            </div>

            <label htmlFor="end_date">End date (optional)</label>
            <input
              id="end_date"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </>
        )}

        <label htmlFor="mobility_need">Mobility need</label>
        <select
          id="mobility_need"
          value={mobilityNeed}
          onChange={(e) => setMobilityNeed(e.target.value)}
        >
          <option value="">None</option>
          {MOBILITY_NEEDS.map((need) => (
            <option key={need.value} value={need.value}>
              {need.label}
            </option>
          ))}
        </select>

        <label htmlFor="notes">Notes</label>
        <textarea
          id="notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
        />

        {error && <p className="form-error">{error}</p>}

        <button type="submit" disabled={isSubmitting}>
          {isSubmitting
            ? "Booking..."
            : isRecurring
              ? "Book recurring trips"
              : "Book trip"}
        </button>
      </form>
    </div>
  );
}
