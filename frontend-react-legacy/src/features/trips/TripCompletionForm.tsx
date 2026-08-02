import { useState, type FormEvent } from "react";
import { useCompleteTripMutation } from "./useTrips";

export function TripCompletionForm({
  tripId,
  onCompleted,
}: {
  tripId: string;
  onCompleted?: () => void;
}) {
  const completeTrip = useCompleteTripMutation();
  const [odometerStart, setOdometerStart] = useState("");
  const [odometerEnd, setOdometerEnd] = useState("");
  const [attestation, setAttestation] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await completeTrip.mutateAsync({
        id: tripId,
        payload: {
          odometer_start: Number(odometerStart),
          odometer_end: Number(odometerEnd),
          completion_attestation: attestation,
        },
      });
      onCompleted?.();
    } catch {
      setError("Could not complete this trip. Check the odometer readings.");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="auth-form completion-form">
      <label htmlFor="odometer_start">Odometer (start)</label>
      <input
        id="odometer_start"
        type="number"
        min={0}
        value={odometerStart}
        onChange={(e) => setOdometerStart(e.target.value)}
        required
        className="completion-form__field"
      />

      <label htmlFor="odometer_end">Odometer (end)</label>
      <input
        id="odometer_end"
        type="number"
        min={0}
        value={odometerEnd}
        onChange={(e) => setOdometerEnd(e.target.value)}
        required
        className="completion-form__field"
      />

      <label htmlFor="completion_attestation">Rider name (confirms trip completion)</label>
      <input
        id="completion_attestation"
        value={attestation}
        onChange={(e) => setAttestation(e.target.value)}
        required
        className="completion-form__field"
      />

      {error && <p className="form-error">{error}</p>}

      <button type="submit" disabled={completeTrip.isPending}>
        {completeTrip.isPending ? "Completing..." : "Complete trip"}
      </button>
    </form>
  );
}
