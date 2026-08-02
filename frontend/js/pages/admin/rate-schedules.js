import { requireRole } from "../../api/auth.js";
import { listRateSchedules, createRateSchedule } from "../../api/billing.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear, dataTable } from "../../ui/dom.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { formatCurrency, formatDate, MOBILITY_NEEDS, MOBILITY_LABELS } from "../../ui/format.js";
import { showToast } from "../../ui/toast.js";

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);

  const mobilitySelect = qs("#mobility_need");
  for (const need of MOBILITY_NEEDS) {
    mobilitySelect.append(el("option", { value: need.value, text: need.label }));
  }

  const tableContent = qs("#table-content");

  async function load() {
    showLoading(tableContent, "Loading rate schedules...");
    try {
      const data = await listRateSchedules();
      clear(tableContent);
      if (data.results.length === 0) {
        showEmpty(tableContent, "No rate schedules yet.");
        return;
      }
      const rows = data.results.map((schedule) =>
        el("tr", { class: "dispatch-table__row" }, [
          el("td", { text: schedule.mobility_need ? MOBILITY_LABELS[schedule.mobility_need] : "Default" }),
          el("td", { text: formatCurrency(schedule.base_fare) }),
          el("td", { text: formatCurrency(schedule.per_mile_rate) }),
          el("td", { text: formatDate(schedule.effective_from) }),
          el("td", { text: schedule.effective_to ? formatDate(schedule.effective_to) : "—" }),
          el("td", { text: schedule.is_active ? "Yes" : "No" }),
        ])
      );
      tableContent.append(
        dataTable(["Mobility tier", "Base fare", "Per-mile rate", "Effective from", "Effective to", "Active"], rows)
      );
    } catch {
      showError(tableContent, "Could not load rate schedules.");
    }
  }

  const form = qs("#rate-form");
  form.hidden = false;
  const submitBtn = qs("#submit-btn");
  const errorEl = qs("#error");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorEl.hidden = true;
    submitBtn.disabled = true;
    submitBtn.textContent = "Saving...";
    try {
      await createRateSchedule({
        mobility_need: mobilitySelect.value || "",
        base_fare: qs("#base_fare").value,
        per_mile_rate: qs("#per_mile_rate").value,
        effective_from: qs("#effective_from").value,
        effective_to: null,
        is_active: true,
      });
      qs("#base_fare").value = "";
      qs("#per_mile_rate").value = "";
      qs("#effective_from").value = "";
      load();
      showToast("Rate schedule added.", { type: "success" });
    } catch {
      errorEl.textContent = "Could not create that rate schedule. Check the values and try again.";
      errorEl.hidden = false;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Add rate schedule";
    }
  });

  load();
}
