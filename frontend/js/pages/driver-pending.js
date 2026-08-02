import { requireRole, logout } from "../api/auth.js";
import { getMyDriverProfile } from "../api/drivers.js";
import { qs, el } from "../ui/dom.js";

// What an admin needs on file before they can approve a driver.
const REQUIRED = [
  ["license_number", "License number"],
  ["license_expiry_date", "License expiry date"],
  ["vehicle_type", "Vehicle type"],
  ["vehicle_plate", "Vehicle plate"],
  ["insurance_document", "Insurance document"],
];

const user = await requireRole(["DRIVER"]);
if (user) {
  try {
    const profile = await getMyDriverProfile();
    if (profile.is_approved) {
      window.location.replace("/driver/index.html");
    } else {
      renderChecklist(profile);
    }
  } catch {
    // If the profile fetch fails, stay on this page rather than bounce the user around.
  }

  // Review can't finish while something is missing, so name what's outstanding
  // instead of leaving the driver waiting on a document nobody asked them for.
  function renderChecklist(profile) {
    const missing = REQUIRED.filter(([key]) => !profile[key]);
    if (missing.length === 0) return;
    qs("#checklist").replaceChildren(
      el("p", { class: "page-status-note", text: "Still needed before an administrator can approve you:" }),
      el(
        "ul",
        { class: "pending-checklist" },
        missing.map(([, label]) => el("li", { text: label }))
      )
    );
  }

  qs("#logout-btn").addEventListener("click", async () => {
    await logout();
    window.location.replace("/login.html");
  });
}
