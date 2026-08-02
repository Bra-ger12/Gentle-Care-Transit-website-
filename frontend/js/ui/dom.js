export function qs(selector, root = document) {
  return root.querySelector(selector);
}

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "html") node.innerHTML = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  for (const child of children) {
    if (child === undefined || child === null) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

export function clear(node) {
  node.replaceChildren();
}

export function dataTable(headers, rows) {
  return el("div", { class: "table-wrap" }, [
    el("table", { class: "dispatch-table" }, [
      el("thead", {}, [el("tr", {}, headers.map((h) => el("th", { text: h })))]),
      el("tbody", {}, rows),
    ]),
  ]);
}
