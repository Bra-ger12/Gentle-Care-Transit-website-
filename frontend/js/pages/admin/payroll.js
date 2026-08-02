import { requireRole } from "../../api/auth.js";
import { listAllDrivers } from "../../api/drivers.js";
import {
  listPayRates,
  createPayRate,
  updatePayRate,
  listEarnings,
  generateEarnings,
  markEarningPaid,
} from "../../api/payroll.js";
import { qs, el, clear, dataTable } from "../../ui/dom.js";
import { renderNav } from "../../ui/nav.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { formatCurrency, formatDate, formatDateTime } from "../../ui/format.js";
import { showToast } from "../../ui/toast.js";

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");
  let unpaidOnly = true;

  // --- Pay rates ---

  function rateRows(rates) {
    return rates.map((rate) => {
      const toggle = el("button", {
        class: "btn",
        text: rate.is_active ? "Deactivate" : "Activate",
        onclick: async () => {
          toggle.disabled = true;
          try {
            await updatePayRate(rate.id, { is_active: !rate.is_active });
            showToast(rate.is_active ? "Rate deactivated." : "Rate activated.", { type: "success" });
            load();
          } catch {
            toggle.disabled = false;
            showToast("Could not update that rate.", { type: "error" });
          }
        },
      });

      return el("tr", { class: "dispatch-table__row" }, [
        el("td", { text: rate.driver_name || "All drivers (default)" }),
        el("td", { class: "mono", text: formatCurrency(rate.per_trip_base) }),
        el("td", { class: "mono", text: `${formatCurrency(rate.per_mile_rate)}/mi` }),
        el("td", {
          text: rate.effective_to
            ? `${formatDate(rate.effective_from)} – ${formatDate(rate.effective_to)}`
            : `from ${formatDate(rate.effective_from)}`,
        }),
        el("td", { text: rate.is_active ? "Active" : "Inactive" }),
        el("td", { class: "dispatch-table__actions" }, [toggle]),
      ]);
    });
  }

  function rateForm(drivers) {
    const driverSelect = el(
      "select",
      {},
      [el("option", { value: "", text: "All drivers (default rate)" })].concat(
        drivers.map((d) =>
          el("option", {
            value: String(d.id),
            text: `${d.first_name} ${d.last_name}`.trim() || d.email,
          })
        )
      )
    );
    const base = el("input", { type: "number", step: "0.01", min: "0", required: "required", placeholder: "12.00" });
    const perMile = el("input", { type: "number", step: "0.01", min: "0", required: "required", placeholder: "1.35" });
    const from = el("input", { type: "date", required: "required", value: new Date().toISOString().slice(0, 10) });
    const to = el("input", { type: "date" });
    const errorEl = el("p", { class: "form-error", hidden: "hidden" });
    const submit = el("button", { type: "submit", class: "btn btn--primary", text: "Add pay rate" });

    const form = el("form", { class: "inline-form" }, [
      el("div", { class: "field-row" }, [el("label", { text: "Applies to" }), driverSelect]),
      el("div", { class: "field-row" }, [el("label", { text: "Per completed trip" }), base]),
      el("div", { class: "field-row" }, [el("label", { text: "Per mile" }), perMile]),
      el("div", { class: "field-row" }, [el("label", { text: "Effective from" }), from]),
      el("div", { class: "field-row" }, [el("label", { text: "Effective to (optional)" }), to]),
      el("div", { class: "inline-form__actions" }, [submit]),
      errorEl,
    ]);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorEl.hidden = true;
      submit.disabled = true;
      try {
        await createPayRate({
          driver: driverSelect.value || null,
          per_trip_base: base.value,
          per_mile_rate: perMile.value,
          effective_from: from.value,
          effective_to: to.value || null,
        });
        showToast("Pay rate added.", { type: "success" });
        load();
      } catch {
        errorEl.textContent = "Could not save that pay rate. Check the amounts and dates.";
        errorEl.hidden = false;
        submit.disabled = false;
      }
    });
    return form;
  }

  // --- Earnings ---

  function earningRows(earnings) {
    return earnings.map((earning) => {
      const cell = el("td", { class: "dispatch-table__actions" });
      if (earning.is_paid) {
        cell.append(
          el("span", {
            class: "ops-row__muted",
            text: `Paid ${formatDateTime(earning.paid_at)}${earning.payment_reference ? ` · ${earning.payment_reference}` : ""}`,
          })
        );
      } else {
        const reference = el("input", { type: "text", placeholder: "Payment ref (optional)" });
        const pay = el("button", {
          class: "btn btn--primary",
          text: "Mark paid",
          onclick: async () => {
            pay.disabled = true;
            try {
              await markEarningPaid(earning.id, reference.value.trim());
              showToast("Earning marked paid.", { type: "success" });
              load();
            } catch {
              pay.disabled = false;
              showToast("Could not mark that earning paid.", { type: "error" });
            }
          },
        });
        cell.append(el("div", { class: "reassign" }, [reference, pay]));
      }

      return el("tr", { class: "dispatch-table__row" }, [
        el("td", { text: formatDate(earning.earned_on) }),
        el("td", { text: earning.driver_name }),
        el("td", { text: earning.trip_route }),
        el("td", { class: "mono", text: Number(earning.mileage_snapshot).toFixed(1) }),
        el("td", { class: "mono", text: formatCurrency(earning.total_amount) }),
        cell,
      ]);
    });
  }

  async function load() {
    showLoading(content, "Loading driver pay...");
    try {
      const [rates, earnings, drivers] = await Promise.all([
        listPayRates(),
        listEarnings({ unpaid: unpaidOnly }),
        listAllDrivers(true),
      ]);
      clear(content);

      content.append(el("h2", { text: "Pay rates" }));
      content.append(
        el("p", {
          class: "section-lead",
          text: "A driver earns a flat amount per completed trip plus a per-mile rate. Rates are effective-dated, and a driver-specific rate overrides the default. Earnings already generated keep the rate they were calculated with.",
        })
      );
      if (rates.results.length === 0) {
        showEmpty(content, "No pay rates yet — add a default rate before generating earnings.");
      } else {
        content.append(
          dataTable(["Applies to", "Per trip", "Per mile", "Effective", "State", ""], rateRows(rates.results))
        );
      }
      content.append(rateForm(drivers.results));

      const generateBtn = el("button", {
        class: "btn",
        text: "Generate from completed trips",
        onclick: async () => {
          generateBtn.disabled = true;
          try {
            const result = await generateEarnings();
            showToast(
              result.generated > 0
                ? `${result.generated} earning${result.generated === 1 ? "" : "s"} generated.`
                : "Nothing new to generate.",
              { type: "success" }
            );
            load();
          } catch {
            generateBtn.disabled = false;
            showToast("Could not generate earnings — check a pay rate covers those trips.", { type: "error" });
          }
        },
      });
      const filterBtn = el("button", {
        class: "btn",
        text: unpaidOnly ? "Showing unpaid only" : "Showing all",
        onclick: () => {
          unpaidOnly = !unpaidOnly;
          load();
        },
      });

      content.append(
        el("h2", { text: "Earnings" }),
        el("div", { class: "filter-bar" }, [generateBtn, filterBtn])
      );
      if (earnings.results.length === 0) {
        showEmpty(content, unpaidOnly ? "No unpaid earnings." : "No earnings recorded yet.");
      } else {
        content.append(
          dataTable(["Date", "Driver", "Trip", "Miles", "Total", "Payment"], earningRows(earnings.results))
        );
      }
    } catch {
      showError(content, "Could not load driver pay.");
    }
  }

  load();
}
