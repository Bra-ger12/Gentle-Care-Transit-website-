import { requireRole } from "../../api/auth.js";
import { listDrivers, approveDriver, rejectDriver } from "../../api/drivers.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { licenseBadge } from "../../ui/badges.js";
import { showToast } from "../../ui/toast.js";

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");

  async function load() {
    showLoading(content, "Loading drivers...");
    try {
      const data = await listDrivers();
      clear(content);
      if (data.results.length === 0) {
        showEmpty(content, "No drivers found.");
        return;
      }
      const errorEl = el("p", { class: "form-error", hidden: "hidden" });
      const rows = data.results.map((driver) => {
        const approveBtn = el("button", {
          class: "btn btn--primary",
          text: "Approve",
          disabled: driver.is_approved ? "disabled" : undefined,
          onclick: async () => {
            errorEl.hidden = true;
            try {
              await approveDriver(driver.id);
              load();
              showToast("Driver approved.", { type: "success" });
            } catch {
              errorEl.textContent = "Could not approve this driver.";
              errorEl.hidden = false;
            }
          },
        });
        const rejectBtn = el("button", {
          class: "btn btn--danger",
          text: "Reject",
          onclick: async () => {
            errorEl.hidden = true;
            try {
              await rejectDriver(driver.id);
              load();
              showToast("Driver rejected.", { type: "info" });
            } catch {
              errorEl.textContent = "Could not reject this driver.";
              errorEl.hidden = false;
            }
          },
        });
        const info = el("div", {}, [
          el("strong", { text: `${driver.first_name} ${driver.last_name}` }),
          ` <${driver.email}>`,
          el("br"),
          el("span", {
            text: `Vehicle: ${driver.vehicle_type || "unspecified"} · Background check: ${driver.background_check_status}${
              driver.is_approved ? " · Approved" : ""
            }`,
          }),
        ]);
        const badge = licenseBadge(driver);
        if (badge) info.append(el("br"), badge);
        return el("li", { class: "driver-list__row" }, [info, el("div", { class: "dispatch-table__actions" }, [approveBtn, rejectBtn])]);
      });
      content.append(el("ul", { class: "driver-list" }, rows), errorEl);
    } catch {
      showError(content, "Could not load drivers.");
    }
  }

  load();
}
