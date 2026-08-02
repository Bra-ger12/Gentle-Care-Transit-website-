import { requireApprovedDriver, getMyDriverProfile } from "../../api/drivers.js";
import { getInspectionChecklist, getTodaysInspections, submitInspection } from "../../api/fleet.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { renderHero } from "../../ui/hero.js";
import { showLoading, showError } from "../../ui/status.js";
import { formatDateTime } from "../../ui/format.js";
import { showToast } from "../../ui/toast.js";

const TYPE_LABELS = { PRE_TRIP: "Pre-trip", POST_TRIP: "Post-trip" };

const user = await requireApprovedDriver();
if (user) {
  renderNav(qs("#app-nav"), user);
  renderHero(qs("#dashboard-hero"), {
    eyebrow: "Gentle Care Transit — Driver Portal",
    title: "Daily vehicle check",
    lead: "Walk the vehicle before your first trip and after your last. Anything you flag goes straight to an administrator — a van marked unsafe stays off the road until they clear it.",
  });

  const content = qs("#content");

  function filedCard(inspection) {
    const state = inspection.has_defects
      ? `${inspection.defects.length} defect${inspection.defects.length === 1 ? "" : "s"} reported`
      : "No defects";
    return el("div", { class: `filed${inspection.needs_attention ? " filed--flagged" : ""}` }, [
      el("div", { class: "filed__head" }, [
        el("strong", { text: TYPE_LABELS[inspection.inspection_type] || inspection.inspection_type }),
        el("span", { class: "ops-panel__meta", text: formatDateTime(inspection.performed_at) }),
      ]),
      el("p", { class: "filed__state", text: `${state} · ${inspection.safe_to_operate ? "safe to operate" : "NOT safe to operate"}` }),
      inspection.defect_notes ? el("p", { class: "ops-panel__note", text: inspection.defect_notes }) : null,
      inspection.reviewed_at
        ? el("p", { class: "ops-panel__note", text: `Cleared by an administrator ${formatDateTime(inspection.reviewed_at)}.` })
        : inspection.needs_attention
          ? el("p", { class: "record__reason", text: "Awaiting administrator review." })
          : null,
    ]);
  }

  function form(checklist, profile, filed) {
    const alreadyFiled = new Set(filed.map((i) => i.inspection_type));

    const typeSelect = el(
      "select",
      { id: "inspection_type" },
      checklist.inspection_types.map((t) =>
        el("option", {
          value: t.value,
          // Default to whichever check is still outstanding today.
          selected: !alreadyFiled.has(t.value) ? "selected" : undefined,
          text: alreadyFiled.has(t.value) ? `${t.label} (replaces today's)` : t.label,
        })
      )
    );

    const odometer = el("input", { type: "number", min: "0", id: "odometer", required: "required" });
    const notes = el("textarea", { rows: "3", id: "defect_notes", placeholder: "Describe anything you flagged" });
    const signature = el("input", {
      type: "text",
      id: "signature",
      required: "required",
      value: `${user.first_name} ${user.last_name}`.trim(),
    });

    const boxes = checklist.items.map((item) => {
      const input = el("input", { type: "checkbox", value: item.value });
      return { value: item.value, input, node: el("label", { class: "settings-check" }, [input, item.label]) };
    });

    const safe = el("input", { type: "checkbox", id: "safe_to_operate" });
    safe.checked = true;

    const errorEl = el("p", { class: "form-error", hidden: "hidden" });
    const submit = el("button", { type: "submit", class: "btn btn--primary", text: "Submit vehicle check" });

    const formEl = el("form", { class: "settings-card__form" }, [
      el("div", { class: "field-row" }, [el("label", { text: "Inspection" }), typeSelect]),
      el("div", { class: "field-row" }, [
        el("label", { text: "Vehicle" }),
        el("p", {
          class: "settings-note",
          text: [profile?.vehicle_type, profile?.vehicle_plate].filter(Boolean).join(" · ") || "No vehicle on file",
        }),
      ]),
      el("div", { class: "field-row" }, [el("label", { text: "Odometer" }), odometer]),
      el("div", { class: "field-row" }, [
        el("label", { text: "Tick anything defective" }),
        el("div", { class: "settings-checks dvir-checks" }, boxes.map((b) => b.node)),
      ]),
      el("div", { class: "field-row" }, [el("label", { text: "Defect notes" }), notes]),
      el("div", { class: "field-row" }, [
        el("label", { text: "Condition" }),
        el("div", { class: "settings-checks settings-checks--stacked" }, [
          el("label", { class: "settings-check" }, [safe, "This vehicle is safe to operate"]),
        ]),
      ]),
      el("div", { class: "field-row" }, [el("label", { text: "Signature (type your name)" }), signature]),
      el("div", { class: "settings-card__actions" }, [submit]),
      errorEl,
    ]);

    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorEl.hidden = true;
      const defects = boxes.filter((b) => b.input.checked).map((b) => b.value);
      if (defects.length > 0 && !notes.value.trim()) {
        errorEl.textContent = "Describe the defect you found so it can be fixed.";
        errorEl.hidden = false;
        return;
      }
      submit.disabled = true;
      submit.textContent = "Submitting...";
      try {
        await submitInspection({
          inspection_type: typeSelect.value,
          odometer: Number(odometer.value),
          defects,
          defect_notes: notes.value.trim(),
          safe_to_operate: safe.checked,
          signature: signature.value.trim(),
        });
        showToast("Vehicle check filed.", { type: "success" });
        load();
      } catch {
        errorEl.textContent = "Could not file this vehicle check. Check the odometer and try again.";
        errorEl.hidden = false;
        submit.disabled = false;
        submit.textContent = "Submit vehicle check";
      }
    });

    return el("section", { class: "settings-card" }, [el("h2", { text: "Today's check" }), formEl]);
  }

  async function load() {
    showLoading(content, "Loading the checklist...");
    try {
      const [checklist, filed, profile] = await Promise.all([
        getInspectionChecklist(),
        getTodaysInspections(),
        getMyDriverProfile().catch(() => null),
      ]);
      clear(content);

      if (filed.length > 0) {
        content.append(
          el("h2", { text: "Filed today" }),
          el("div", { class: "filed-list" }, filed.map(filedCard))
        );
      }
      content.append(form(checklist, profile, filed));
      content.append(
        el("a", { class: "ops-workflow__link", href: "/driver/index.html", text: "← Back to today's board" })
      );
    } catch {
      showError(content, "Could not load the vehicle checklist.");
    }
  }

  load();
}
