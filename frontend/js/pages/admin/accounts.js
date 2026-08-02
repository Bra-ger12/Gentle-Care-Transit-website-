import { requireRole } from "../../api/auth.js";
import { listUsers, suspendUser, activateUser } from "../../api/drivers.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear, dataTable } from "../../ui/dom.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { showToast } from "../../ui/toast.js";

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");

  async function load() {
    const role = qs("#role-filter").value || undefined;
    const q = qs("#q").value.trim() || undefined;
    showLoading(content, "Loading accounts...");
    try {
      const data = await listUsers({ role, q });
      clear(content);
      if (data.results.length === 0) {
        showEmpty(content, "No accounts match.");
        return;
      }
      const errorEl = el("p", { class: "form-error", hidden: "hidden" });
      const rows = data.results.map((account) => {
        const isAdmin = account.role === "ADMIN";
        const statusPill = el("span", {
          class: `trip-status ${account.is_active ? "trip-status--completed" : "trip-status--cancelled"}`,
          text: account.is_active ? "Active" : "Suspended",
        });
        const actionBtn = el("button", {
          class: account.is_active ? "btn btn--danger" : "btn btn--primary",
          text: account.is_active ? "Suspend" : "Activate",
          disabled: isAdmin ? "disabled" : undefined,
          title: isAdmin ? "Admin accounts can't be suspended here" : undefined,
          onclick: async () => {
            errorEl.hidden = true;
            actionBtn.disabled = true;
            try {
              if (account.is_active) await suspendUser(account.id);
              else await activateUser(account.id);
              showToast(account.is_active ? "Account suspended." : "Account activated.", {
                type: account.is_active ? "info" : "success",
              });
              load();
            } catch {
              errorEl.textContent = "Could not update this account.";
              errorEl.hidden = false;
              actionBtn.disabled = false;
            }
          },
        });
        return el("tr", { class: "dispatch-table__row" }, [
          el("td", { text: account.full_name || "—" }),
          el("td", { class: "mono", text: account.email }),
          el("td", { text: account.role }),
          el("td", {}, [statusPill]),
          el("td", { class: "dispatch-table__actions" }, [actionBtn]),
        ]);
      });
      content.append(dataTable(["Name", "Email", "Role", "Status", ""], rows), errorEl);
    } catch {
      showError(content, "Could not load accounts.");
    }
  }

  qs("#filter-form").addEventListener("submit", (event) => {
    event.preventDefault();
    load();
  });

  load();
}
