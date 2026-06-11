const form = document.getElementById("search-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const submitBtn = form.querySelector("button");
const addressInput = document.getElementById("address");
const autocompleteList = document.getElementById("autocomplete-list");
const themeToggle = document.getElementById("theme-toggle");
const filterWrapper = document.getElementById("filter-wrapper");
const keywordFilter = document.getElementById("keyword-filter");
const mapEl = document.getElementById("map");
const mapSection = document.getElementById("map-section");
const mapToggle = document.getElementById("map-toggle");
const dayToggleSwitch = document.getElementById("day-toggle-switch");
const dayToggleLabels = document.querySelectorAll(".day-toggle-label");

const THEME_KEY = "garage-sale-theme";
const ADDRESS_KEY = "garage-sale-address";
const MAP_COLLAPSED_KEY = "garage-sale-map-collapsed";

const OMAHA_CENTER = [41.2565, -95.9345];

const PLACEHOLDER_IMAGE = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 88 88'%3E%3Crect width='88' height='88' fill='%23e0e0e0'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' font-size='12' fill='%23999' font-family='sans-serif'%3ENo photo%3C/text%3E%3C/svg%3E";

let autocompleteTimer = null;
let activeSuggestionIndex = -1;
let currentListings = [];
let selectedDay = "today";
let map = null;
let userMarker = null;
let listingMarkersLayer = null;
let pendingUserLocation = null;

const savedAddress = localStorage.getItem(ADDRESS_KEY);
if (savedAddress) {
    addressInput.value = savedAddress;
}

if (localStorage.getItem(MAP_COLLAPSED_KEY) === "1") {
    mapSection.classList.add("collapsed");
    mapToggle.textContent = "Show map";
} else {
    ensureMap();
}

mapToggle.addEventListener("click", () => {
    const collapsed = mapSection.classList.toggle("collapsed");
    mapToggle.textContent = collapsed ? "Show map" : "Hide map";
    localStorage.setItem(MAP_COLLAPSED_KEY, collapsed ? "1" : "0");

    if (!collapsed) {
        ensureMap();
        requestAnimationFrame(() => map.invalidateSize());
    }
});

form.addEventListener("submit", (event) => {
    event.preventDefault();
    performSearch();
});

dayToggleSwitch.addEventListener("click", () => {
    selectedDay = selectedDay === "today" ? "tomorrow" : "today";
    updateDayToggle();
});

function updateDayToggle() {
    const isTomorrow = selectedDay === "tomorrow";
    dayToggleSwitch.setAttribute("aria-checked", String(isTomorrow));
    dayToggleLabels.forEach((label) => {
        label.classList.toggle("active", label.dataset.day === selectedDay);
    });
}

async function performSearch() {
    const address = addressInput.value.trim();
    if (!address) return;

    localStorage.setItem(ADDRESS_KEY, address);

    clearAutocomplete();
    resultsEl.innerHTML = "";
    filterWrapper.hidden = true;
    keywordFilter.value = "";
    submitBtn.disabled = true;
    setStatus(`Searching... the first search for ${dayLabel()} can take up to a minute.`);

    try {
        const response = await fetch(`/api/listings?address=${encodeURIComponent(address)}&day=${selectedDay}`);
        const data = await response.json();

        if (!response.ok) {
            setStatus(data.error || "Something went wrong.", true);
            return;
        }

        currentListings = data.listings;
        filterWrapper.hidden = !currentListings.length;
        renderResults(currentListings);
        updateMapMarkers(currentListings);

        if (data.user_location) {
            setUserLocation(data.user_location.lat, data.user_location.lon);
        }
    } catch (err) {
        setStatus("Couldn't reach the server. Please try again.", true);
    } finally {
        submitBtn.disabled = false;
    }
}

function dayLabel() {
    return selectedDay === "tomorrow" ? "tomorrow" : "today";
}

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

keywordFilter.addEventListener("input", () => {
    const query = keywordFilter.value.trim().toLowerCase();

    if (!query) {
        renderResults(currentListings);
        updateMapMarkers(currentListings);
        return;
    }

    const filtered = currentListings.filter((listing) => {
        const haystack = `${listing.title} ${listing.description} ${listing.location}`.toLowerCase();
        return haystack.includes(query);
    });

    renderResults(filtered, currentListings.length);
    updateMapMarkers(filtered);
});

themeToggle.addEventListener("click", () => {
    const isLight = document.documentElement.getAttribute("data-theme") === "light";
    applyTheme(isLight ? "dark" : "light");
});

function ensureMap() {
    if (map) return;

    map = L.map(mapEl).setView(OMAHA_CENTER, 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    listingMarkersLayer = L.layerGroup().addTo(map);

    if (pendingUserLocation) {
        setUserLocation(pendingUserLocation.lat, pendingUserLocation.lon);
    }
    updateMapMarkers(currentListings);
}

function setUserLocation(lat, lon) {
    pendingUserLocation = { lat, lon };
    if (!map) return;

    map.setView([lat, lon], 13);

    if (userMarker) {
        userMarker.setLatLng([lat, lon]);
    } else {
        userMarker = L.marker([lat, lon], {
            icon: L.divIcon({ className: "user-location-marker", iconSize: [16, 16] }),
        }).addTo(map).bindPopup("Your location");
    }
}

function updateMapMarkers(listings) {
    if (!listingMarkersLayer) return;

    listingMarkersLayer.clearLayers();

    listings.forEach((listing) => {
        if (listing.lat === null || listing.lon === null) return;

        L.marker([listing.lat, listing.lon])
            .addTo(listingMarkersLayer)
            .bindPopup(`<strong>${escapeHtml(listing.title)}</strong><br>${escapeHtml(listing.location || "")}`);
    });
}

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

function renderResults(listings, totalCount = null) {
    if (!listings.length) {
        setStatus(totalCount === null
            ? `No garage sales found for ${dayLabel()}. Check back later!`
            : "No garage sales match that filter.");
        resultsEl.innerHTML = "";
        return;
    }

    if (totalCount === null) {
        setStatus(`Found ${listings.length} garage sale${listings.length === 1 ? "" : "s"} for ${dayLabel()}.`);
    } else {
        setStatus(`Showing ${listings.length} of ${totalCount} garage sale${totalCount === 1 ? "" : "s"}.`);
    }

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
