import { completeTrip } from "../../api/trips.js";
import { el } from "../../ui/dom.js";
import { clearFormErrors, showFormError } from "../../ui/form-errors.js";
import { signaturePad } from "../../ui/signature-pad.js";
import { showToast } from "../../ui/toast.js";

/**
 * The drop-off record: odometer pair, typed name, and the rider's drawn mark.
 *
 * The signature is optional on purpose. It is the strongest evidence a claim can
 * carry, so it's offered first and prompted for — but a rider in a cast, a
 * cracked screen, or a January morning in Minot are all real, and a driver who
 * genuinely can't collect one must still be able to close out the trip. The
 * typed attestation remains the fallback, and the Medicaid export says which
 * of the two it is rather than implying a signature exists.
 */
export function tripCompletionForm(tripId, onCompleted) {
  const odometerStart = el("input", {
    type: "number",
    min: "0",
    required: "required",
    id: `odo-start-${tripId}`,
  });
  const odometerEnd = el("input", {
    type: "number",
    min: "0",
    required: "required",
    id: `odo-end-${tripId}`,
  });
  const attestation = el("input", {
    type: "text",
    required: "required",
    id: `attest-${tripId}`,
    autocomplete: "off",
  });
  const errorEl = el("p", { class: "form-error", hidden: "hidden", role: "alert" });
  const submitBtn = el("button", {
    type: "submit",
    class: "btn btn--primary",
    text: "Complete trip",
  });

  const pad = signaturePad({
    label: "Rider signature",
    hint: "Ask the rider to sign. If they can't, leave it blank — the typed name still stands.",
  });

  const fields = {
    odometer_start: odometerStart,
    odometer_end: odometerEnd,
    completion_attestation: attestation,
  };

  const form = el(
    "form",
    {
      class: "inline-form completion-form",
      onsubmit: async (event) => {
        event.preventDefault();
        clearFormErrors(errorEl, fields);
        submitBtn.disabled = true;
        submitBtn.textContent = "Completing...";

        const payload = {
          odometer_start: Number(odometerStart.value),
          odometer_end: Number(odometerEnd.value),
          completion_attestation: attestation.value.trim(),
        };
        const signature = pad.toDataURL();
        if (signature) payload.signature_image = signature;

        try {
          await completeTrip(tripId, payload);
          showToast("Trip completed.", { type: "success" });
          onCompleted?.();
        } catch (error) {
          showFormError(errorEl, error, fields);
          submitBtn.disabled = false;
          submitBtn.textContent = "Complete trip";
        }
      },
    },
    [
      el("div", { class: "field-pair" }, [
        el("label", { class: "field-row" }, ["Odometer at pickup", odometerStart]),
        el("label", { class: "field-row" }, ["Odometer at drop-off", odometerEnd]),
      ]),
      el("label", { class: "field-row" }, ["Rider name", attestation]),
      pad.element,
      submitBtn,
      errorEl,
    ]
  );

  return form;
}
