import { requireRole } from "../../api/auth.js";
import { listAuditLogs } from "../../api/audit.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear, dataTable } from "../../ui/dom.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { renderPagination } from "../../ui/pagination.js";
import { formatDateTime } from "../../ui/format.js";

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");
  let page = 1;

  async function load() {
    showLoading(content, "Loading audit log...");
    try {
      const data = await listAuditLogs({
        page,
        action: qs("#action").value || undefined,
        modelName: qs("#model_name").value || undefined,
      });
      clear(content);
      if (data.results.length === 0) {
        showEmpty(content, "No matching audit log entries.");
      } else {
        const rows = data.results.map((entry) =>
          el("tr", { class: "dispatch-table__row" }, [
            el("td", { text: formatDateTime(entry.timestamp) }),
            el("td", { text: entry.actor_email || "—" }),
            el("td", { text: entry.action }),
            el("td", { text: entry.model_name }),
            el("td", { text: entry.object_id }),
          ])
        );
        content.append(dataTable(["Timestamp", "Actor", "Action", "Model", "Object ID"], rows));
      }
      const paginationEl = el("div", {});
      content.append(paginationEl);
      renderPagination(
        paginationEl,
        data,
        () => {
          page -= 1;
          load();
        },
        () => {
          page += 1;
          load();
        }
      );
    } catch {
      showError(content, "Could not load the audit log.");
    }
  }

  qs("#action").addEventListener("change", () => {
    page = 1;
    load();
  });
  qs("#model_name").addEventListener("input", () => {
    page = 1;
    load();
  });

  load();
}
