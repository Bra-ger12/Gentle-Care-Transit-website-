import { requireRole, updateCurrentUser } from "../api/auth.js";
import {
  getMyRiderProfile,
  updateMyRiderProfile,
  getMyDriverProfile,
  updateMyDriverProfile,
} from "../api/drivers.js";
import { getNotificationPreferences, updateNotificationPreferences } from "../api/notifications.js";
import { renderNav } from "../ui/nav.js";
import { qs, el, clear } from "../ui/dom.js";
import { renderHero } from "../ui/hero.js";
import { showLoading, showError } from "../ui/status.js";
import { MOBILITY_NEEDS, formatDate } from "../ui/format.js";
import { showToast } from "../ui/toast.js";
import { verificationNotice } from "./shared/verification-notice.js";

const VEHICLE_TYPES = [
  ["", "Unspecified"],
  ["SEDAN", "Sedan"],
  ["WHEELCHAIR_VAN", "Wheelchair van"],
  ["STRETCHER_VAN", "Stretcher van"],
];

const BACKGROUND_CHECK_LABELS = {
  PENDING: "Pending",
  APPROVED: "Approved",
  REJECTED: "Rejected",
};

const user = await requireRole(["RIDER", "DRIVER", "ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  renderHero(qs("#dashboard-hero"), {
    eyebrow: "Gentle Care Transit — Your account",
    title: "Account settings",
    lead: "Keep your contact details, care needs and alert preferences up to date — dispatch and your driver use exactly what's here.",
  });

  const content = qs("#content");

  // --- Small form helpers, shared by every section on the page ---

  const field = (label, input) => el("div", { class: "field-row" }, [el("label", { text: label }), input]);

  const textInput = (value, attrs = {}) =>
    el("input", { type: "text", value: value ?? "", ...attrs });

  const checkbox = (label, checked) => {
    const input = el("input", { type: "checkbox" });
    input.checked = Boolean(checked);
    return { input, node: el("label", { class: "settings-check" }, [input, label]) };
  };

  const select = (options, current) =>
    el(
      "select",
      {},
      options.map(([value, label]) =>
        el("option", { value, selected: (current || "") === value ? "selected" : undefined, text: label })
      )
    );

  /**
   * A settings card: heading, fields, one save button. `save` receives no
   * arguments and throws to signal failure; the button handles its own state.
   */
  function settingsCard({ title, lead, fields, saveLabel = "Save changes", save }) {
    const errorEl = el("p", { class: "form-error", hidden: "hidden" });
    const button = el("button", {
      class: "btn btn--primary",
      type: "submit",
      text: saveLabel,
    });

    const form = el("form", { class: "settings-card__form" }, [...fields, el("div", { class: "settings-card__actions" }, [button]), errorEl]);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorEl.hidden = true;
      button.disabled = true;
      button.textContent = "Saving...";
      try {
        await save();
        showToast("Saved.", { type: "success" });
      } catch (error) {
        errorEl.replaceChildren(...fieldErrors(error));
        errorEl.hidden = false;
      } finally {
        button.disabled = false;
        button.textContent = saveLabel;
      }
    });

    return el("section", { class: "settings-card" }, [
      el("h2", { text: title }),
      lead ? el("p", { class: "section-lead", text: lead }) : null,
      form,
    ]);
  }

  /**
   * Surface DRF's per-field validation messages instead of a generic failure.
   * Nested shapes are flattened — a list field reports per-index errors as
   * `{"mobility_needs": {"0": ["..."]}}`, not a flat array of strings.
   */
  function flattenMessages(value) {
    if (value === null || value === undefined) return [];
    if (Array.isArray(value)) return value.flatMap(flattenMessages);
    if (typeof value === "object") return Object.values(value).flatMap(flattenMessages);
    return [String(value)];
  }

  function fieldErrors(error) {
    const data = error && error.data;
    if (!data || typeof data !== "object") {
      return [el("span", { text: "Could not save your changes. Please try again." })];
    }
    const items = Object.entries(data).flatMap(([key, value]) =>
      flattenMessages(value).map((message) =>
        el("li", { text: key === "non_field_errors" ? message : `${key.replaceAll("_", " ")}: ${message}` })
      )
    );
    return items.length > 0 ? [el("ul", {}, items)] : [el("span", { text: "Could not save your changes." })];
  }

  // --- Sections ---

  function accountCard(me) {
    const firstName = textInput(me.first_name, { required: "required" });
    const lastName = textInput(me.last_name, { required: "required" });
    const email = el("input", { type: "email", value: me.email || "", required: "required" });
    const phone = el("input", { type: "tel", value: me.phone_number || "", placeholder: "+17015550100" });

    return settingsCard({
      title: "Your details",
      lead: `Signed in as ${me.email} · member since ${formatDate(me.date_joined)}.`,
      fields: [
        field("First name", firstName),
        field("Last name", lastName),
        field("Email", email),
        field("Phone number", phone),
      ],
      save: () =>
        updateCurrentUser({
          first_name: firstName.value.trim(),
          last_name: lastName.value.trim(),
          email: email.value.trim(),
          phone_number: phone.value.trim(),
        }),
    });
  }

  function riderCard(profile) {
    const dob = el("input", { type: "date", value: profile.date_of_birth || "" });
    const address1 = textInput(profile.address_line1);
    const address2 = textInput(profile.address_line2, { placeholder: "Apt, suite (optional)" });
    const city = textInput(profile.city);
    const state = textInput(profile.state, { maxlength: "2", placeholder: "ND" });
    const zip = textInput(profile.zip_code, { maxlength: "10" });
    const contactName = textInput(profile.emergency_contact_name);
    const contactPhone = el("input", { type: "tel", value: profile.emergency_contact_phone || "" });
    const medicaid = textInput(profile.medicaid_id, { placeholder: "Leave blank if not applicable" });
    // Standing and long-distance NEMT trips need a prior authorisation number on
    // the claim; it is snapshotted onto each invoice as it is generated.
    const priorAuth = textInput(profile.prior_auth_number, {
      placeholder: "If your plan issued one",
    });

    const needs = MOBILITY_NEEDS.map((need) => ({
      value: need.value,
      ...checkbox(need.label, (profile.mobility_needs || []).includes(need.value)),
    }));
    const needsGroup = el("div", { class: "settings-checks" }, needs.map((n) => n.node));

    return settingsCard({
      title: "Care & contact details",
      lead: "Your driver sees your mobility needs; dispatch calls your emergency contact if they can't reach you.",
      fields: [
        field("Date of birth", dob),
        field("Address", address1),
        field("Address line 2", address2),
        field("City", city),
        field("State", state),
        field("ZIP code", zip),
        field("Emergency contact name", contactName),
        field("Emergency contact phone", contactPhone),
        el("div", { class: "field-row" }, [el("label", { text: "Mobility needs" }), needsGroup]),
        field("Medicaid ID", medicaid),
        field("Prior authorisation number", priorAuth),
        el("p", {
          class: "settings-note",
          text: "A Medicaid ID on file is what puts your completed trips on the ND NEMT reimbursement export.",
        }),
      ],
      save: () =>
        updateMyRiderProfile({
          date_of_birth: dob.value || null,
          address_line1: address1.value.trim(),
          address_line2: address2.value.trim(),
          city: city.value.trim(),
          state: state.value.trim().toUpperCase(),
          zip_code: zip.value.trim(),
          emergency_contact_name: contactName.value.trim(),
          emergency_contact_phone: contactPhone.value.trim(),
          mobility_needs: needs.filter((n) => n.input.checked).map((n) => n.value),
          medicaid_id: medicaid.value.trim() || null,
          prior_auth_number: priorAuth.value.trim(),
        }),
    });
  }

  function driverCard(profile) {
    const licenseNumber = textInput(profile.license_number);
    const licenseExpiry = el("input", { type: "date", value: profile.license_expiry_date || "" });
    const vehicleType = select(VEHICLE_TYPES, profile.vehicle_type);
    const vehiclePlate = textInput(profile.vehicle_plate, { placeholder: "e.g. ND 4821-K" });
    const vehicleCapacity = el("input", {
      type: "number",
      min: "1",
      value: profile.vehicle_capacity ?? "",
      placeholder: "seats",
    });
    const insurance = el("input", { type: "file", accept: ".pdf,.png,.jpg,.jpeg" });

    const status = el("p", { class: "settings-note" }, [
      `Approval: ${profile.is_approved ? "approved" : "pending admin review"} · background check: ${
        BACKGROUND_CHECK_LABELS[profile.background_check_status] || profile.background_check_status
      }`,
      profile.insurance_document
        ? el("span", {}, [" · ", el("a", { href: profile.insurance_document, target: "_blank", rel: "noopener", text: "current insurance document" })])
        : " · no insurance document on file",
    ]);

    return settingsCard({
      title: "License & vehicle",
      lead: "Admins review these before approving you to drive; an expired license takes you off the assignment list.",
      fields: [
        status,
        field("License number", licenseNumber),
        field("License expiry", licenseExpiry),
        field("Vehicle type", vehicleType),
        field("Plate", vehiclePlate),
        field("Capacity (seats)", vehicleCapacity),
        field("Replace insurance document", insurance),
      ],
      save: () => {
        const payload = {
          license_number: licenseNumber.value.trim(),
          license_expiry_date: licenseExpiry.value || null,
          vehicle_type: vehicleType.value,
          vehicle_plate: vehiclePlate.value.trim(),
          vehicle_capacity: vehicleCapacity.value ? Number(vehicleCapacity.value) : null,
        };
        const file = insurance.files && insurance.files[0];
        if (!file) return updateMyDriverProfile(payload);

        // A document upload has to go as multipart; nulls can't ride along in a form.
        const form = new FormData();
        for (const [key, value] of Object.entries(payload)) {
          if (value !== null && value !== "") form.append(key, value);
        }
        form.append("insurance_document", file);
        return updateMyDriverProfile(form, true);
      },
    });
  }

  function preferencesCard(prefs) {
    const email = checkbox("Email me trip updates and reminders", prefs.email_enabled);
    const sms = checkbox("Text me trip updates and reminders", prefs.sms_enabled);

    return settingsCard({
      title: "Notification preferences",
      lead: "In-app notifications always stay on — they're the record of what we sent you.",
      saveLabel: "Save preferences",
      fields: [el("div", { class: "settings-checks settings-checks--stacked" }, [email.node, sms.node])],
      save: () =>
        updateNotificationPreferences({
          email_enabled: email.input.checked,
          sms_enabled: sms.input.checked,
        }),
    });
  }

  // --- Load ---

  showLoading(content, "Loading your account...");
  try {
    const [profile, prefs] = await Promise.all([
      user.role === "RIDER"
        ? getMyRiderProfile()
        : user.role === "DRIVER"
          ? getMyDriverProfile()
          : Promise.resolve(null),
      getNotificationPreferences().catch(() => ({ email_enabled: true, sms_enabled: true })),
    ]);

    clear(content);
    // The way out of an unverified account, offered where someone goes to fix
    // their details rather than only where they are blocked.
    const notice = verificationNotice(user);
    if (notice) content.append(notice);
    content.append(accountCard(user));
    if (user.role === "RIDER" && profile) content.append(riderCard(profile));
    if (user.role === "DRIVER" && profile) content.append(driverCard(profile));
    content.append(preferencesCard(prefs));
  } catch {
    showError(content, "Could not load your account settings.");
  }
}
