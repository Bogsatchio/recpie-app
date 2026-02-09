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
const SUGGESTION_ENDPOINT = "/ingredients/suggestions";
const SUGGESTION_DELAY = 250;
const SUGGESTION_MIN_CHARS = 2;
const SUGGESTION_LIMIT = 5;

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

function readIngredientTags(container) {
  if (!container) {
    return [];
  }
  return Array.from(container.querySelectorAll("[data-ingredient-chip]"))
    .map((chip) => chip.dataset.value || chip.textContent || "")
    .map((item) => cleanListItem(item))
    .filter(Boolean);
}

function getIngredientHidden(container) {
  return container?.closest("label")?.querySelector("[data-ingredient-hidden]") || null;
}

function updateIngredientHidden(container) {
  const hidden = getIngredientHidden(container);
  if (hidden) {
    hidden.value = readIngredientTags(container).join(", ");
  }
}

function addIngredientChips(container, items) {
  if (!container || !items) {
    return;
  }
  const chipsWrap = container.querySelector("[data-ingredient-chips]");
  if (!chipsWrap) {
    return;
  }
  const existing = new Set(readIngredientTags(container).map((item) => item.toLowerCase()));
  items.forEach((item) => {
    const cleaned = cleanListItem(item);
    if (!cleaned) {
      return;
    }
    const key = cleaned.toLowerCase();
    if (existing.has(key)) {
      return;
    }
    existing.add(key);

    const chip = document.createElement("span");
    chip.className = "ingredient-chip";
    chip.dataset.ingredientChip = "true";
    chip.dataset.value = cleaned;
    chip.textContent = cleaned;

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "ingredient-remove";
    removeBtn.setAttribute("aria-label", `Remove ${cleaned}`);
    removeBtn.textContent = "x";
    chip.appendChild(removeBtn);
    chipsWrap.appendChild(chip);
  });
  updateIngredientHidden(container);
}

function commitIngredientEntry(container) {
  if (!container) {
    return;
  }
  const entry = container.querySelector("[data-ingredient-entry]");
  if (!entry) {
    return;
  }
  const items = parseList(entry.value);
  if (items.length) {
    addIngredientChips(container, items);
    entry.value = "";
  } else {
    entry.value = entry.value.trim();
  }
  clearSuggestions(container);
}

function getIngredientTags(form) {
  if (!form) {
    return [];
  }
  const container = form.querySelector("[data-ingredient-input]");
  if (!container) {
    return [];
  }
  commitIngredientEntry(container);
  return readIngredientTags(container);
}

function getSuggestionContainer(container) {
  return container?.closest("label")?.querySelector("[data-ingredient-suggestions]") || null;
}

function clearSuggestions(container) {
  const suggestionBox = getSuggestionContainer(container);
  if (!suggestionBox) {
    return;
  }
  suggestionBox.classList.remove("active");
  suggestionBox.innerHTML = "";
}

function renderSuggestions(container, suggestions) {
  const suggestionBox = getSuggestionContainer(container);
  if (!suggestionBox) {
    return;
  }
  suggestionBox.innerHTML = "";
  if (!suggestions.length) {
    suggestionBox.classList.remove("active");
    return;
  }
  suggestions.forEach((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "ingredient-suggestion";
    button.dataset.value = item;
    button.textContent = item;
    suggestionBox.appendChild(button);
  });
  suggestionBox.classList.add("active");
}

function buildSuggestionParams(query, exclude, limit) {
  const params = new URLSearchParams();
  params.set("q", query);
  if (limit) {
    params.set("limit", String(limit));
  }
  if (exclude && exclude.length) {
    params.set("exclude", exclude.join(", "));
  }
  return params.toString();
}

async function fetchSuggestions(query, exclude, limit) {
  try {
    const params = buildSuggestionParams(query, exclude, limit);
    const response = await fetch(`${SUGGESTION_ENDPOINT}?${params}`);
    if (!response.ok) {
      return [];
    }
    const data = await response.json().catch(() => ({}));
    if (data && Array.isArray(data.suggestions)) {
      return data.suggestions;
    }
    return [];
  } catch (error) {
    return [];
  }
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

const ingredientInputs = document.querySelectorAll("[data-ingredient-input]");
ingredientInputs.forEach((container) => {
  const entry = container.querySelector("[data-ingredient-entry]");
  const addButton = container.querySelector("[data-ingredient-add]");
  const suggestionBox = getSuggestionContainer(container);
  let suggestionTimer = null;
  let requestId = 0;

  const hidden = getIngredientHidden(container);
  if (hidden && hidden.value) {
    addIngredientChips(container, parseList(hidden.value));
  }

  if (suggestionBox) {
    suggestionBox.addEventListener("mousedown", (event) => {
      event.preventDefault();
    });
    suggestionBox.addEventListener("click", (event) => {
      const target = event.target;
      if (target instanceof HTMLElement && target.matches(".ingredient-suggestion")) {
        event.preventDefault();
        const value = target.dataset.value || target.textContent || "";
        addIngredientChips(container, [value]);
        if (entry) {
          entry.value = "";
          entry.focus();
        }
        clearSuggestions(container);
      }
    });
  }

  container.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.matches(".ingredient-remove")) {
      event.preventDefault();
      const chip = target.closest("[data-ingredient-chip]");
      if (chip) {
        chip.remove();
        updateIngredientHidden(container);
      }
      return;
    }
  });

  if (entry) {
    const scheduleSuggestions = () => {
      const query = entry.value.trim();
      if (query.length < SUGGESTION_MIN_CHARS) {
        clearSuggestions(container);
        return;
      }
      if (suggestionTimer) {
        clearTimeout(suggestionTimer);
      }
      suggestionTimer = setTimeout(async () => {
        const currentId = ++requestId;
        const exclude = readIngredientTags(container);
        const suggestions = await fetchSuggestions(query, exclude, SUGGESTION_LIMIT);
        if (currentId !== requestId) {
          return;
        }
        const filtered = suggestions.filter(
          (item) => !exclude.some((excludeItem) => excludeItem.toLowerCase() === String(item).toLowerCase())
        );
        renderSuggestions(container, filtered);
      }, SUGGESTION_DELAY);
    };

    entry.addEventListener("keydown", (event) => {
      if (event.key === ",") {
        event.preventDefault();
        commitIngredientEntry(container);
        return;
      }
      if (event.key === "Enter" && entry.value.trim()) {
        event.preventDefault();
        commitIngredientEntry(container);
        return;
      }
      if (event.key === "Backspace" && !entry.value) {
        const chips = container.querySelectorAll("[data-ingredient-chip]");
        const lastChip = chips[chips.length - 1];
        if (lastChip) {
          lastChip.remove();
          updateIngredientHidden(container);
        }
      }
      if (event.key === "Escape") {
        clearSuggestions(container);
      }
    });
    entry.addEventListener("input", scheduleSuggestions);
    entry.addEventListener("focus", scheduleSuggestions);
    entry.addEventListener("blur", () => commitIngredientEntry(container));
  }

  if (addButton) {
    addButton.addEventListener("click", () => commitIngredientEntry(container));
  }
});

const ingredientsForm = document.getElementById("ingredients-form");
if (ingredientsForm) {
  ingredientsForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(ingredientsForm);
    const ingredients = getIngredientTags(ingredientsForm);
    if (!ingredients.length) {
      renderEmpty("Please enter at least one ingredient.");
      return;
    }

    const params = new URLSearchParams();
    params.set("ingredients", ingredients.join(", "));
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
    const ingredients = getIngredientTags(nameForm);
    if (ingredients.length) {
      ingredients.forEach((item) => params.append("ingredients", item));
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
