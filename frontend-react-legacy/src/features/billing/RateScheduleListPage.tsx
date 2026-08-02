import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { MOBILITY_NEEDS } from "../trips/constants";
import { useCreateRateScheduleMutation, useRateSchedulesQuery } from "./useBilling";

export function RateScheduleListPage() {
  const { data, isLoading, isError } = useRateSchedulesQuery();
  const createRateSchedule = useCreateRateScheduleMutation();

  const [mobilityNeed, setMobilityNeed] = useState("");
  const [baseFare, setBaseFare] = useState("");
  const [perMileRate, setPerMileRate] = useState("");
  const [effectiveFrom, setEffectiveFrom] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await createRateSchedule.mutateAsync({
        mobility_need: mobilityNeed,
        base_fare: baseFare,
        per_mile_rate: perMileRate,
        effective_from: effectiveFrom,
        effective_to: null,
        is_active: true,
      });
      setBaseFare("");
      setPerMileRate("");
      setEffectiveFrom("");
    } catch {
      setError("Could not create that rate schedule. Check the values and try again.");
    }
  }

  if (isLoading) {
    return <div className="page-status">Loading rate schedules...</div>;
  }
  if (isError) {
    return <div className="page-status">Could not load rate schedules.</div>;
  }

  const schedules = data?.results ?? [];

  return (
    <div className="portal-page">
      <h1>Rate schedules</h1>
      <p>
        <Link to="/admin/billing/invoices">Invoices</Link> &middot;{" "}
        <Link to="/admin/billing/medicaid-export">Medicaid export</Link>
      </p>

      <table className="dispatch-table">
        <thead>
          <tr>
            <th>Mobility tier</th>
            <th>Base fare</th>
            <th>Per-mile rate</th>
            <th>Effective from</th>
            <th>Effective to</th>
            <th>Active</th>
          </tr>
        </thead>
        <tbody>
          {schedules.map((schedule) => (
            <tr key={schedule.id} className="dispatch-table__row">
              <td>{schedule.mobility_need || "Default"}</td>
              <td>${schedule.base_fare}</td>
              <td>${schedule.per_mile_rate}/mi</td>
              <td>{schedule.effective_from}</td>
              <td>{schedule.effective_to ?? "—"}</td>
              <td>{schedule.is_active ? "Yes" : "No"}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h2>Add a rate schedule</h2>
      <form onSubmit={handleSubmit} className="auth-form">
        <label htmlFor="mobility_need">Mobility tier</label>
        <select
          id="mobility_need"
          value={mobilityNeed}
          onChange={(e) => setMobilityNeed(e.target.value)}
        >
          <option value="">Default (all riders)</option>
          {MOBILITY_NEEDS.map((need) => (
            <option key={need.value} value={need.value}>
              {need.label}
            </option>
          ))}
        </select>

        <label htmlFor="base_fare">Base fare ($)</label>
        <input
          id="base_fare"
          type="number"
          step="0.01"
          min="0"
          value={baseFare}
          onChange={(e) => setBaseFare(e.target.value)}
          required
        />

        <label htmlFor="per_mile_rate">Per-mile rate ($)</label>
        <input
          id="per_mile_rate"
          type="number"
          step="0.01"
          min="0"
          value={perMileRate}
          onChange={(e) => setPerMileRate(e.target.value)}
          required
        />

        <label htmlFor="effective_from">Effective from</label>
        <input
          id="effective_from"
          type="date"
          value={effectiveFrom}
          onChange={(e) => setEffectiveFrom(e.target.value)}
          required
        />

        {error && <p className="form-error">{error}</p>}

        <button type="submit" disabled={createRateSchedule.isPending}>
          {createRateSchedule.isPending ? "Saving..." : "Add rate schedule"}
        </button>
      </form>
    </div>
  );
}
