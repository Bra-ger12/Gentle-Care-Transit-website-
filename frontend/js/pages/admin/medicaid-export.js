import { requireRole } from "../../api/auth.js";
import { downloadMedicaidExport } from "../../api/billing.js";
import { renderNav } from "../../ui/nav.js";
import { qs } from "../../ui/dom.js";
import { showToast } from "../../ui/toast.js";

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  qs("#session-status").hidden = true;
  qs("#export-form").hidden = false;

  const dateFrom = qs("#date_from");
  const dateTo = qs("#date_to");
  const csvBtn = qs("#csv-btn");
  const pdfBtn = qs("#pdf-btn");
  const errorEl = qs("#error");

  function updateButtons() {
    const enabled = Boolean(dateFrom.value && dateTo.value);
    csvBtn.disabled = !enabled;
    pdfBtn.disabled = !enabled;
  }
  dateFrom.addEventListener("input", updateButtons);
  dateTo.addEventListener("input", updateButtons);

  async function download(exportFormat, button) {
    errorEl.hidden = true;
    button.disabled = true;
    try {
      const { blob, filename } = await downloadMedicaidExport(dateFrom.value, dateTo.value, exportFormat);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.append(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      showToast(`${exportFormat.toUpperCase()} export downloaded.`, { type: "success" });
    } catch {
      errorEl.textContent = "Could not generate that export. Check the date range and try again.";
      errorEl.hidden = false;
    } finally {
      updateButtons();
    }
  }

  csvBtn.addEventListener("click", () => download("csv", csvBtn));
  pdfBtn.addEventListener("click", () => download("pdf", pdfBtn));
}
