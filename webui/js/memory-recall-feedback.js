import { callJsonApi } from "./api.js";

/**
 * @param {HTMLElement} container — e.g. process-step-detail-scroll
 * @param {unknown} rawItems — list of { text, memory_id, dataset, context_id, kind } from log kvps
 */
export function mountMemoryRecallFeedback(container, rawItems) {
  if (!container || rawItems == null) return;

  let items = rawItems;
  if (typeof items === "string") {
    try {
      items = JSON.parse(items);
    } catch {
      return;
    }
  }
  if (!Array.isArray(items) || items.length === 0) return;

  let wrap = container.querySelector(".memory-recall-feedback");
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.className = "memory-recall-feedback";
    container.appendChild(wrap);
  }
  wrap.textContent = "";

  const title = document.createElement("div");
  title.className = "memory-recall-feedback-title";
  title.textContent = "Was this recall helpful?";
  wrap.appendChild(title);

  const state = {};

  for (let i = 0; i < items.length; i++) {
    const row = items[i];
    if (!row || typeof row !== "object") continue;
    const mid = String(row.memory_id ?? "");
    const ds = String(row.dataset ?? "");
    const ctx = String(row.context_id ?? "");
    if (!mid || !ds || !ctx) continue;

    const rowEl = document.createElement("div");
    rowEl.className = "memory-recall-feedback-row";

    const snippet = document.createElement("div");
    snippet.className = "memory-recall-feedback-snippet";
    const label =
      row.kind === "solution" ? "Solution" : "Memory";
    snippet.textContent = `${label}: ${String(row.text ?? "").slice(0, 280)}${
      String(row.text ?? "").length > 280 ? "…" : ""
    }`;
    rowEl.appendChild(snippet);

    const actions = document.createElement("div");
    actions.className = "memory-recall-feedback-actions";

    const status = document.createElement("span");
    status.className = "memory-recall-feedback-status";
    const key = `${mid}:${i}`;

    const mkBtn = (feedback, symbol, aria) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "btn btn2 memory-recall-feedback-btn";
      b.setAttribute("aria-label", aria);
      b.textContent = symbol;
      b.addEventListener("click", async () => {
        if (state[key] === "sending" || state[key] === "success") return;
        state[key] = "sending";
        status.textContent = "Sending…";
        b.disabled = true;
        try {
          const out = await callJsonApi("/memory_feedback", {
            context_id: ctx,
            dataset: ds,
            memory_id: mid,
            feedback,
          });
          if (out && out.success) {
            state[key] = "success";
            status.textContent = "Thanks — feedback saved.";
            actions.querySelectorAll("button").forEach((x) => {
              x.disabled = true;
            });
          } else {
            throw new Error(out?.error || "unexpected response");
          }
        } catch (e) {
          state[key] = "error";
          status.textContent = "Could not send feedback; try again.";
          actions.querySelectorAll("button").forEach((x) => {
            x.disabled = false;
          });
        }
      });
      return b;
    };

    actions.appendChild(mkBtn("positive", "👍", "Mark recall as helpful"));
    actions.appendChild(mkBtn("negative", "👎", "Mark recall as not helpful"));
    actions.appendChild(status);

    rowEl.appendChild(actions);
    wrap.appendChild(rowEl);
  }
}
