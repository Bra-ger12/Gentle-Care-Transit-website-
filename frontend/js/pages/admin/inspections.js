import { requireRole } from "../../api/auth.js";
import { listInspections, reviewInspection, getInspectionChecklist } from "../../api/fleet.js";
import { qs, el, clear } from "../../ui/dom.js";
import { renderNav } from "../../ui/nav.js";
import { showLoading, showError, showEmpty } from "../../ui/status.js";
import { renderPagination } from "../../ui/pagination.js";
import { formatDateTime } from "../../ui/format.js";
import { showToast } from "../../ui/toast.js";

const TYPE_LABELS = { PRE_TRIP: "Pre-trip", POST_TRIP: "Post-trip" };

const user = await requireRole(["ADMIN"]);
if (user) {
  renderNav(qs("#app-nav"), user);
  const content = qs("#content");
  let page = 1;
  let outstandingOnly = true;
  let labels = {};

  function inspectionCard(inspection) {
    const card = el(
      "article",
      { class: `filed${inspection.needs_attention ? " filed--flagged" : ""}` },
      [
        el("div", { class: "filed__head" }, [
          el("strong", { text: inspection.driver_name }),
          el("span", {
            class: "ops-panel__meta",
            text: `${TYPE_LABELS[inspection.inspection_type] || inspection.inspection_type} · ${formatDateTime(inspection.performed_at)}`,
          }),
        ]),
        el("p", { class: "filed__state" }, [
          el("span", {
            text: [
              inspection.vehicle_plate_snapshot || "No plate on file",
              `${inspection.odometer.toLocaleString()} mi`,
              inspection.safe_to_operate ? "safe to operate" : "NOT safe to operate",
            ].join(" · "),
          }),
        ]),
      ]
    );

    if (inspection.defects.length > 0) {
      card.append(
        el(
          "div",
          { class: "settings-checks" },
          inspection.defects.map((d) => el("span", { class: "chip chip--alert", text: labels[d] || d }))
        )
      );
    }
    if (inspection.defect_notes) {
      card.append(el("p", { class: "ops-panel__note", text: inspection.defect_notes }));
    }
    card.append(el("p", { class: "ops-panel__note", text: `Signed: ${inspection.signature}` }));

    if (inspection.reviewed_at) {
      card.append(
        el("p", { class: "ops-panel__note", text: `Cleared ${formatDateTime(inspection.reviewed_at)}` }),
        inspection.resolution_notes ? el("p", { class: "rating-review", text: inspection.resolution_notes }) : null
      );
    } else if (inspection.needs_attention) {
      const notes = el("input", { type: "text", placeholder: "What was done about it" });
      const clearBtn = el("button", {
        class: "btn btn--primary",
        text: "Mark resolved",
        onclick: async () => {
          clearBtn.disabled = true;
          try {
            await reviewInspection(inspection.id, notes.value.trim());
            showToast("Inspection cleared.", { type: "success" });
            load();
          } catch {
            clearBtn.disabled = false;
            showToast("Could not clear that inspection.", { type: "error" });
          }
        },
      });
      card.append(el("div", { class: "reassign" }, [notes, clearBtn]));
    }
    return card;
  }

  async function load() {
    showLoading(content, "Loading inspections...");
    try {
      if (!labels.BRAKES) {
        const checklist = await getInspectionChecklist().catch(() => ({ items: [] }));
        labels = Object.fromEntries(checklist.items.map((i) => [i.value, i.label]));
      }
      const data = await listInspections({ page, needsAttention: outstandingOnly });
      clear(content);

      const toggle = el("button", {
        class: "btn",
        text: outstandingOnly ? "Showing defects needing action" : "Showing all reports",
        onclick: () => {
          outstandingOnly = !outstandingOnly;
          page = 1;
          load();
        },
      });
      content.append(
        el("p", {
          class: "section-lead",
          text: "Drivers file a pre-trip and post-trip check each day. Anything flagged stays here until an administrator records what was done about it.",
        }),
        el("div", { class: "filter-bar" }, [toggle])
      );

      if (data.results.length === 0) {
        showEmpty(
          content,
          outstandingOnly ? "No outstanding defects — every flagged report has been cleared." : "No inspections filed yet."
        );
        return;
      }

      content.append(el("div", { class: "filed-list" }, data.results.map(inspectionCard)));

      const paginationEl = el("div", { id: "pagination" });
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
      showError(content, "Could not load inspections.");
    }
  }

  load();
}
