import { requireRole } from "../../api/auth.js";
import { listInvoices, generateInvoices } from "../../api/billing.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear, dataTable } from "../../ui/dom.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { renderPagination } from "../../ui/pagination.js";
import { invoiceStatusBadge } from "../../ui/badges.js";
import { formatCurrency, formatDate } from "../../ui/format.js";
import { showToast } from "../../ui/toast.js";

export async function run(role) {
  const user = await requireRole([role]);
  if (!user) return;
  renderNav(qs("#app-nav"), user);

  const isAdmin = role === "ADMIN";
  const detailBase = isAdmin ? "/admin/invoice-detail.html" : "/rider/invoice-detail.html";
  const heading = qs("#heading");
  heading.textContent = isAdmin ? "Invoices" : "Your invoices";

  if (isAdmin) {
    qs("#admin-nav").hidden = false;
    const generateBtn = qs("#generate-btn");
    const generateError = qs("#generate-error");
    generateBtn.addEventListener("click", async () => {
      generateError.hidden = true;
      generateBtn.disabled = true;
      generateBtn.textContent = "Generating...";
      try {
        const created = await generateInvoices(undefined);
        load();
        showToast(`${created.length} invoice${created.length === 1 ? "" : "s"} generated.`, { type: "success" });
      } catch {
        generateError.textContent = "Could not generate invoices.";
        generateError.hidden = false;
      } finally {
        generateBtn.disabled = false;
        generateBtn.textContent = "Generate invoices for completed trips";
      }
    });
  }

  const content = qs("#content");
  let page = 1;

  async function load() {
    showLoading(content, "Loading invoices...");
    try {
      const data = await listInvoices(page);
      clear(content);
      if (data.results.length === 0) {
        showEmpty(content, "No invoices yet.");
      } else {
        const rows = data.results.map((invoice) =>
          el("tr", { class: "dispatch-table__row" }, [
            el("td", {}, [el("a", { href: `${detailBase}?id=${invoice.id}`, text: invoice.invoice_number })]),
            el("td", { text: invoice.rider_name_snapshot }),
            el("td", {}, [invoiceStatusBadge(invoice.status)]),
            el("td", { text: formatCurrency(invoice.total_amount) }),
            el("td", { text: formatDate(invoice.created_at) }),
          ])
        );
        content.append(dataTable(["Invoice #", "Rider", "Status", "Total", "Created"], rows));
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
      showError(content, "Could not load invoices.");
    }
  }

  load();
}
