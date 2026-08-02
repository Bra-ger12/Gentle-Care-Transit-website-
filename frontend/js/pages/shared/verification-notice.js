import { resendVerificationEmail } from "../../api/auth.js";
import { el } from "../../ui/dom.js";
import { errorMessage } from "../../ui/form-errors.js";
import { showToast } from "../../ui/toast.js";

/**
 * The banner an unverified rider sees, with the way out built into it.
 *
 * Returns null for anyone already confirmed, so callers can append it
 * unconditionally. Telling someone their account is limited without giving them
 * the button that fixes it is the version of this that wastes a phone call to
 * dispatch.
 */
export function verificationNotice(user) {
  if (!user || user.is_verified) return null;

  const resend = el("button", {
    type: "button",
    class: "btn btn--primary btn--small",
    text: "Send it again",
    onclick: async () => {
      resend.disabled = true;
      resend.textContent = "Sending...";
      try {
        const response = await resendVerificationEmail();
        showToast(response.detail || "Link sent.", { type: "success" });
        resend.textContent = "Sent — check your inbox";
      } catch (error) {
        showToast(errorMessage(error, "Could not send that email."), { type: "error" });
        resend.disabled = false;
        resend.textContent = "Send it again";
      }
    },
  });

  return el("div", { class: "verify-banner", role: "status" }, [
    el("div", { class: "verify-banner__text" }, [
      el("strong", { text: "Confirm your email address to book trips." }),
      el("p", {
        text: `We sent a link to ${user.email}. It also switches on trip confirmations, driver updates and appointment reminders.`,
      }),
    ]),
    resend,
  ]);
}
