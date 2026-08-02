import { confirmEmail, resendVerificationEmail, bootSession, ROLE_HOME } from "../api/auth.js";
import { qs, el, clear } from "../ui/dom.js";
import { errorMessage } from "../ui/form-errors.js";
import { showToast } from "../ui/toast.js";

/**
 * The page the emailed confirmation link opens.
 *
 * Deliberately works signed out: the link is normally clicked in a mail client,
 * often on a phone that has never had this site open. It confirms first and asks
 * about signing in afterwards, so nobody is bounced to a login screen holding a
 * one-time token they can't use twice.
 */

const content = qs("#content");
const params = new URLSearchParams(window.location.search);
const uid = params.get("uid");
const token = params.get("token");

function actions(user) {
  const home = user ? ROLE_HOME[user.role] : null;
  return el("div", { class: "pending-actions" }, [
    home
      ? el("a", { class: "btn btn--primary", href: home, text: "Go to your dashboard" })
      : el("a", { class: "btn btn--primary", href: "/login.html", text: "Sign in" }),
    el("a", { class: "btn", href: "/", text: "Return home" }),
  ]);
}

function succeeded(detail, user) {
  clear(content);
  content.append(
    el("p", { class: "notice-page__glyph", text: "✓", "aria-hidden": "true" }),
    el("h1", { text: "Email confirmed" }),
    el("p", { class: "page-status-note", text: detail }),
    el("p", {
      class: "page-status-note",
      text: "You can now book trips, and we'll send you confirmations and reminders.",
    }),
    actions(user)
  );
}

function failed(message, user) {
  clear(content);
  const block = el("div", {}, [
    el("h1", { text: "That link didn't work" }),
    el("p", { class: "form-error", text: message }),
  ]);

  // Only offer a resend to someone we can identify; an anonymous visitor has no
  // address for us to send to, and guessing one would be worse than saying so.
  if (user) {
    const resend = el("button", {
      class: "btn btn--primary",
      text: "Send me a new link",
      onclick: async () => {
        resend.disabled = true;
        resend.textContent = "Sending...";
        try {
          const response = await resendVerificationEmail();
          showToast(response.detail || "Link sent.", { type: "success" });
          resend.textContent = "Link sent — check your inbox";
        } catch (error) {
          showToast(errorMessage(error, "Could not send that email."), { type: "error" });
          resend.disabled = false;
          resend.textContent = "Send me a new link";
        }
      },
    });
    block.append(el("div", { class: "pending-actions" }, [resend]));
  } else {
    block.append(
      el("p", {
        class: "page-status-note",
        text: "Sign in and request a fresh link from your account page.",
      }),
      actions(null)
    );
  }
  content.append(block);
}

// A session may or may not exist; either is fine, so a failure here is not fatal.
const user = await bootSession().catch(() => null);

if (!uid || !token) {
  failed("This link is missing part of its address. Open it straight from the email.", user);
} else {
  try {
    const response = await confirmEmail(uid, token);
    succeeded(response.detail || "Your email address is confirmed.", user);
  } catch (error) {
    failed(errorMessage(error, "This link has expired or has already been used."), user);
  }
}
