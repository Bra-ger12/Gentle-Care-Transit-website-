import { requireRole, getCurrentUser } from "../../api/auth.js";
import { loadServiceAreaSummary } from "../../api/operations.js";
import { renderNav } from "../../ui/nav.js";
import { qs, el, clear } from "../../ui/dom.js";
import { bookingForm } from "../shared/booking-form.js";
import { verificationNotice } from "../shared/verification-notice.js";

const user = await requireRole(["RIDER"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");

  const [policy, me] = await Promise.all([
    loadServiceAreaSummary(),
    getCurrentUser().catch(() => user),
  ]);

  clear(content);

  // An unverified rider can't book, and finding that out only after filling the
  // whole form in would be a poor way to learn it.
  const notice = verificationNotice(me);
  if (notice) content.append(notice);

  if (policy?.enforced && policy.areas?.length) {
    content.append(
      el("p", { class: "queue-note" }, [
        el("strong", { text: "We serve: " }),
        policy.areas.map((area) => area.name).join(", "),
        ". Trips starting or ending outside these areas can't be booked here — call dispatch on ",
        el("a", { href: "tel:+17015550100", text: "(701) 555-0100" }),
        ".",
      ])
    );
  }

  const presetDropoff = new URLSearchParams(location.search).get("dropoff") || "";

  content.append(
    bookingForm({
      policy,
      presetDropoff,
      onBooked: () => window.location.replace("/rider/index.html"),
    })
  );
}
