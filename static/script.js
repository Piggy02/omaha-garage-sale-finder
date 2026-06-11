const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const submitBtn = form.querySelector("button");
const addressInput = document.getElementById("address");
const autocompleteList = document.getElementById("autocomplete-list");
const themeToggle = document.getElementById("theme-toggle");

const THEME_KEY = "garage-sale-theme";

const PLACEHOLDER_IMAGE = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 88 88'%3E%3Crect width='88' height='88' fill='%23e0e0e0'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='12' fill='%23999' font-family='sans-serif'%3ENo photo%3C/text%3E%3C/svg%3E";

let autocompleteTimer = null;
let activeSuggestionIndex = -1;

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const address = addressInput.value.trim();
    if (!address) return;

    clearAutocomplete();
    resultsEl.innerHTML = "";
    submitBtn.disabled = true;
    setStatus("Searching... the first search of the day can take up to a minute.");

    try {
        const response = await fetch(`/api/listings?address=${encodeURIComponent(address)}`);
        const data = await response.json();

        if (!response.ok) {
            setStatus(data.error || "Something went wrong.", true);
            return;
        }

        renderResults(data.listings);
    } catch (err) {
        setStatus("Couldn't reach the server. Please try again.", true);
    } finally {
        submitBtn.disabled = false;
    }
});

addressInput.addEventListener("input", () => {
    const query = addressInput.value.trim();

    clearTimeout(autocompleteTimer);

    if (query.length < 3) {
        clearAutocomplete();
        return;
    }

    autocompleteTimer = setTimeout(() => fetchSuggestions(query), 350);
});

addressInput.addEventListener("keydown", (event) => {
    const items = autocompleteList.querySelectorAll("li");
    if (!items.length) return;

    if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveSuggestion(items, activeSuggestionIndex + 1);
    } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveSuggestion(items, activeSuggestionIndex - 1);
    } else if (event.key === "Enter") {
        if (activeSuggestionIndex >= 0) {
            event.preventDefault();
            items[activeSuggestionIndex].click();
        }
    } else if (event.key === "Escape") {
        clearAutocomplete();
    }
});

document.addEventListener("click", (event) => {
    if (!event.target.closest(".address-wrapper")) {
        clearAutocomplete();
    }
});

resultsEl.addEventListener("click", (event) => {
    if (event.target.classList.contains("description-toggle")) {
        const description = event.target.previousElementSibling;
        const expanded = description.classList.toggle("expanded");
        event.target.textContent = expanded ? "Show less" : "Show more";
    }
});

themeToggle.addEventListener("click", () => {
    const isLight = document.documentElement.getAttribute("data-theme") === "light";
    applyTheme(isLight ? "dark" : "light");
});

function applyTheme(theme) {
    if (theme === "light") {
        document.documentElement.setAttribute("data-theme", "light");
    } else {
        document.documentElement.removeAttribute("data-theme");
    }
    localStorage.setItem(THEME_KEY, theme);
}

async function fetchSuggestions(query) {
    try {
        const response = await fetch(`/api/autocomplete?q=${encodeURIComponent(query)}`);
        if (!response.ok) return;
        const data = await response.json();
        renderSuggestions(data.suggestions || []);
    } catch (err) {
        clearAutocomplete();
    }
}

function renderSuggestions(suggestions) {
    activeSuggestionIndex = -1;

    if (!suggestions.length) {
        clearAutocomplete();
        return;
    }

    autocompleteList.innerHTML = suggestions.map((s) => `<li>${escapeHtml(s)}</li>`).join("");

    autocompleteList.querySelectorAll("li").forEach((li, index) => {
        li.addEventListener("click", () => {
            addressInput.value = suggestions[index];
            clearAutocomplete();
            addressInput.focus();
        });
    });
}

function setActiveSuggestion(items, index) {
    if (index < 0) index = items.length - 1;
    if (index >= items.length) index = 0;

    items.forEach((item) => item.classList.remove("active"));
    items[index].classList.add("active");
    items[index].scrollIntoView({ block: "nearest" });
    activeSuggestionIndex = index;
}

function clearAutocomplete() {
    autocompleteList.innerHTML = "";
    activeSuggestionIndex = -1;
}

function setStatus(message, isError = false) {
    statusEl.textContent = message;
    statusEl.classList.toggle("error", isError);
}

function renderResults(listings) {
    if (!listings.length) {
        setStatus("No garage sales found for today. Check back later!");
        return;
    }

    setStatus(`Found ${listings.length} garage sale${listings.length === 1 ? "" : "s"} today.`);

    resultsEl.innerHTML = listings.map((listing) => {
        const distance = listing.distance_miles !== null
            ? `<span class="listing-distance">${listing.distance_miles} mi away</span>`
            : `<span>Distance unknown</span>`;

        const dates = listing.sale_dates.length
            ? listing.sale_dates.join(", ")
            : "Date not specified";

        const directions = listing.maps_url
            ? `<a class="directions-link" href="${listing.maps_url}" target="_blank" rel="noopener">Directions</a>`
            : "";

        const source = listing.source
            ? `<span class="listing-source">Source: ${escapeHtml(listing.source)}</span>`
            : "";

        const description = listing.description
            ? `
                <p class="listing-description">${escapeHtml(listing.description)}</p>
                <button type="button" class="description-toggle">Show more</button>
            `
            : "";

        const imageUrl = listing.image_url || PLACEHOLDER_IMAGE;

        return `
            <li class="listing-card">
                <img class="listing-thumb" src="${imageUrl}" alt="" loading="lazy" onerror="this.src='${PLACEHOLDER_IMAGE}'">
                <div class="listing-content">
                    <p class="listing-title"><a href="${listing.url}" target="_blank" rel="noopener">${escapeHtml(listing.title)}</a></p>
                    <p class="listing-meta">${escapeHtml(listing.location || "Location not specified")}</p>
                    <p class="listing-meta">Sale date(s): ${escapeHtml(dates)}</p>
                    <p class="listing-meta">${distance}</p>
                    ${description}
                    <div class="listing-footer">
                        ${source}
                        ${directions}
                    </div>
                </div>
            </li>
        `;
    }).join("");
}

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
}
