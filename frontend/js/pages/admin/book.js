import { requireRole } from "../../api/auth.js";
import { listUsers } from "../../api/drivers.js";
import { loadServiceAreaSummary } from "../../api/operations.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { showError, showLoading } from "../../ui/status.js";
import { bookingForm } from "../shared/booking-form.js";
import { showToast } from "../../ui/toast.js";

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");

  /**
   * Riders are listed by user account, but a trip belongs to a RiderProfile, so
   * the option values are profile ids. A rider who has somehow never had a
   * profile created is skipped rather than offered and then rejected on submit.
   */
  async function riderOptions() {
    const page = await listUsers({ role: "RIDER" });
    return (page.results || [])
      .filter((row) => row.is_active && row.riderprofile_id != null)
      .map((row) => ({
        id: row.riderprofile_id,
        name: row.full_name || row.email,
        phone: row.phone_number,
      }));
  }

  async function load() {
    showLoading(content, "Loading riders...");
    try {
      const [riders, policy] = await Promise.all([riderOptions(), loadServiceAreaSummary()]);
      clear(content);

      if (riders.length === 0) {
        content.append(
          el("p", { class: "queue-note" }, [
            "No active rider accounts to book for. ",
            el("a", { href: "/admin/accounts.html", text: "Manage accounts" }),
          ])
        );
        return;
      }

      if (policy?.enforced && policy.areas?.length) {
        content.append(
          el("p", { class: "queue-note" }, [
            el("strong", { text: "Service area: " }),
            policy.areas.map((area) => area.name).join(", "),
            ".",
          ])
        );
      }

      content.append(
        bookingForm({
          riders,
          policy,
          onBooked: () => {
            showToast("Trip booked for the rider.", { type: "success" });
            window.location.replace("/admin/index.html");
          },
        })
      );
    } catch {
      showError(content, "Could not load the rider list.");
    }
  }

  load();
}
