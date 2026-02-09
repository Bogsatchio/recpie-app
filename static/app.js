"use strict";

const buttons = document.querySelectorAll(".mode-btn");
const panels = document.querySelectorAll(".panel-content");
const resultsMeta = document.getElementById("results-meta");
const resultsBody = document.getElementById("results");
const addMessage = document.getElementById("add-message");

const columns = [
  { key: "name", label: "Name" },
  { key: "rating_value", label: "Rating" },
  { key: "rating_count", label: "Rating Count" },
  { key: "cuisine", label: "Cuisine" },
  { key: "preparation_time", label: "Preparation Time" },
  { key: "ingredients", label: "Ingredients" },
];

const listFields = new Set(["ingredients", "ingredients_raw", "instructions", "cooking_methods", "implements"]);

function setActivePanel(panelId) {
  buttons.forEach((btn) => btn.classList.toggle("active", btn.dataset.panel === panelId));
  panels.forEach((panel) => panel.classList.toggle("active", panel.dataset.panel === panelId));
}

buttons.forEach((btn) => {
  btn.addEventListener("click", () => setActivePanel(btn.dataset.panel));
});

function parseList(value) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseQuotedList(value) {
  const items = [];
  const regex = /'([^']*)'|"([^"]*)"/g;
  let match;
  while ((match = regex.exec(value)) !== null) {
    const item = match[1] ?? match[2];
    if (item && item.trim()) {
      items.push(item.trim());
    }
  }
  return items;
}

function cleanListItem(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value)
    .trim()
    .replace(/^[\s\[\]'"`,]+/, "")
    .replace(/[\s\[\]'"`,]+$/, "")
    .trim();
}

function normalizeIngredientsList(value) {
  if (Array.isArray(value)) {
    return value.map((item) => cleanListItem(item)).filter(Boolean);
  }
  if (value === null || value === undefined) {
    return [];
  }
  if (typeof value !== "string") {
    return [];
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return [];
  }
  if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
    const inner = trimmed.slice(1, -1);
    const quoted = parseQuotedList(inner).map((item) => cleanListItem(item)).filter(Boolean);
    if (quoted.length) {
      const remainder = inner
        .replace(/'[^']*'|"[^"]*"/g, " ")
        .replace(/[\[\],]/g, " ")
        .trim();
      const tail = remainder ? parseList(remainder).map((item) => cleanListItem(item)).filter(Boolean) : [];
      return [...quoted, ...tail];
    }
    return parseList(inner).map((item) => cleanListItem(item)).filter(Boolean);
  }
  return parseList(trimmed).map((item) => cleanListItem(item)).filter(Boolean);
}

function getSelectedValues(selectEl) {
  if (!selectEl) {
    return [];
  }
  return Array.from(selectEl.selectedOptions)
    .map((option) => option.value)
    .filter(Boolean);
}

function setStatus(message, type) {
  if (!addMessage) {
    return;
  }
  addMessage.textContent = message;
  addMessage.classList.remove("success", "error");
  if (type) {
    addMessage.classList.add(type);
  }
}

function formatValue(value, key) {
  if (Array.isArray(value)) {
    const joiner = key === "instructions" ? " | " : ", ";
    return value.join(joiner);
  }
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

function renderEmpty(message) {
  resultsBody.innerHTML = `<div class="empty">${message}</div>`;
}

function renderResults(items) {
  if (!items || items.length === 0) {
    resultsMeta.textContent = "No matches yet.";
    renderEmpty("No matches found.");
    return;
  }

  resultsMeta.textContent = `${items.length} match${items.length === 1 ? "" : "es"} found.`;
  const table = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");

  columns.forEach((col) => {
    const th = document.createElement("th");
    th.textContent = col.label;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);
  table.appendChild(thead);

  const tbody = document.createElement("tbody");
  items.forEach((item) => {
    const row = document.createElement("tr");
    columns.forEach((col) => {
      const cell = document.createElement("td");
      if (col.key === "ingredients") {
        const ingredients = normalizeIngredientsList(item[col.key]);
        if (ingredients.length) {
          const list = document.createElement("ul");
          list.classList.add("cell-list");
          ingredients.forEach((ingredient) => {
            const li = document.createElement("li");
            li.textContent = ingredient;
            list.appendChild(li);
          });
          cell.appendChild(list);
        } else {
          cell.textContent = formatValue(item[col.key], col.key);
        }
      } else {
        cell.textContent = formatValue(item[col.key], col.key);
      }
      if (col.key === "ingredients") {
        cell.classList.add("cell-wrap");
      }
      row.appendChild(cell);
    });
    tbody.appendChild(row);
  });

  table.appendChild(tbody);
  resultsBody.innerHTML = "";
  resultsBody.appendChild(table);
}

async function runQuery(endpoint, params) {
  resultsMeta.textContent = "Searching...";
  renderEmpty("Working on it...");
  const url = `${endpoint}?${params.toString()}`;

  try {
    const response = await fetch(url);
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || "Request failed");
    }
    const data = await response.json();
    renderResults(data.results || []);
  } catch (error) {
    resultsMeta.textContent = "Something went wrong.";
    renderEmpty(error.message);
  }
}

const ingredientsForm = document.getElementById("ingredients-form");
if (ingredientsForm) {
  ingredientsForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(ingredientsForm);
    const ingredients = String(formData.get("ingredients") || "").trim();
    if (!ingredients) {
      renderEmpty("Please enter at least one ingredient.");
      return;
    }

    const params = new URLSearchParams();
    params.set("ingredients", ingredients);
    const k = String(formData.get("k") || "").trim();
    if (k) {
      params.set("k", k);
    }
    const category = String(formData.get("category") || "").trim();
    if (category) {
      params.set("category", category);
    }
    const cuisine = String(formData.get("cuisine") || "").trim();
    if (cuisine) {
      params.set("cuisine", cuisine);
    }

    runQuery("/query_by_ingredients", params);
  });
}

const nameForm = document.getElementById("name-form");
if (nameForm) {
  nameForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(nameForm);
    const name = String(formData.get("name") || "").trim();
    if (!name) {
      renderEmpty("Please enter a recipe name.");
      return;
    }

    const params = new URLSearchParams();
    params.set("name", name);
    const k = String(formData.get("k") || "").trim();
    if (k) {
      params.set("k", k);
    }
    const category = String(formData.get("category") || "").trim();
    if (category) {
      params.set("category", category);
    }
    const cuisine = String(formData.get("cuisine") || "").trim();
    if (cuisine) {
      params.set("cuisine", cuisine);
    }
    const ingredients = String(formData.get("ingredients") || "").trim();
    if (ingredients) {
      parseList(ingredients).forEach((item) => params.append("ingredients", item));
    }

    runQuery("/query_by_name", params);
  });
}

const addForm = document.getElementById("add-form");
if (addForm) {
  addForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setStatus("Submitting recipe...", null);

    const formData = new FormData(addForm);
    const payload = {};

    const requiredFields = ["name", "ingredients", "ingredients_raw", "instructions"];
    for (const field of requiredFields) {
      const value = String(formData.get(field) || "").trim();
      if (!value) {
        setStatus(`Please fill in ${field.replace("_", " ")}.`, "error");
        return;
      }
      payload[field] = listFields.has(field) ? parseList(value) : value;
    }

    const cuisineValue = String(formData.get("cuisine") || "").trim();
    if (!cuisineValue) {
      setStatus("Please choose a cuisine.", "error");
      return;
    }
    payload.cuisine = cuisineValue;

    const categorySelect = addForm.querySelector('select[name="category"]');
    const categoryValues = getSelectedValues(categorySelect);
    if (!categoryValues.length) {
      setStatus("Please choose at least one category.", "error");
      return;
    }
    payload.category = categoryValues;

    const optionalNumbers = ["preparation_time", "cooking_time", "number_of_steps"];
    for (const field of optionalNumbers) {
      const value = String(formData.get(field) || "").trim();
      if (value) {
        const numberValue = Number(value);
        if (Number.isNaN(numberValue)) {
          setStatus(`Invalid number for ${field.replace("_", " ")}.`, "error");
          return;
        }
        payload[field] = numberValue;
      }
    }

    const optionalTextAreas = ["cooking_methods", "implements"];
    optionalTextAreas.forEach((field) => {
      const value = String(formData.get(field) || "").trim();
      if (value) {
        payload[field] = parseList(value);
      }
    });

    const urlValue = String(formData.get("url") || "").trim();
    if (urlValue) {
      payload.url = urlValue;
    }

    const nutritionValue = String(formData.get("nutrition") || "").trim();
    if (nutritionValue) {
      try {
        payload.nutrition = JSON.parse(nutritionValue);
      } catch (error) {
        setStatus("Nutrition must be valid JSON.", "error");
        return;
      }
    }

    try {
      const response = await fetch("/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || "Recipe could not be added.");
      }
      setStatus(`Recipe added successfully. ID: ${data.recipe_id}`, "success");
    } catch (error) {
      setStatus(error.message, "error");
    }
  });
}
