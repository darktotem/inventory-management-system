const LOW_STOCK = 10; // items below this count as "low stock"

const authSection = document.getElementById("authSection");
const appSection = document.getElementById("appSection");
const userBadge = document.getElementById("userBadge");
const notice = document.getElementById("notice");
const itemList = document.getElementById("itemList");
const itemSearch = document.getElementById("itemSearch");
const stockFilter = document.getElementById("stockFilter");

let allItems = [];
let lastFound = null; // last product returned by /external/search
let noticeTimer = null;

// One helper for every request. Returns the response and its JSON body.
async function api(url, options = {}) {
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });

    const data = await response.json().catch(() => ({}));
    return { response, data };
}

function showNotice(text, ok = true) {
    notice.textContent = text;
    notice.className = `notice ${ok ? "ok" : "error"}`;
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => notice.classList.add("hidden"), 5000);
}

function money(value) {
    return `KES ${Number(value).toLocaleString("en-KE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

async function checkLogin() {
    const { data } = await api("/me");

    if (data.logged_in) {
        authSection.classList.add("hidden");
        appSection.classList.remove("hidden");
        userBadge.classList.remove("hidden");
        userBadge.textContent = `Logged in: ${data.username}`;
        await loadItems();
    } else {
        authSection.classList.remove("hidden");
        appSection.classList.add("hidden");
        userBadge.classList.add("hidden");
    }
}

// LOGIN / LOGOUT
document.getElementById("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    const { response, data } = await api("/login", {
        method: "POST",
        body: JSON.stringify({
            username: document.getElementById("loginUsername").value,
            password: document.getElementById("loginPassword").value,
        }),
    });

    const message = document.getElementById("loginMessage");
    message.textContent = data.message || data.error || "Something went wrong";
    message.style.color = response.ok ? "#18794e" : "#b42318";

    if (response.ok) {
        event.target.reset();
        await checkLogin();
    }
});

document.getElementById("logoutButton").addEventListener("click", async () => {
    await api("/logout", { method: "POST" });
    await checkLogin();
});


// READ: GET /inventory
async function loadItems() {
    const { response, data } = await api("/inventory");
    if (!response.ok) {
        showNotice(data.error || "Could not load inventory", false);
        return;
    }

    allItems = data;
    renderStats();
    renderItems();
}

function renderStats() {
    const units = allItems.reduce((sum, item) => sum + item.stock, 0);
    const value = allItems.reduce((sum, item) => sum + item.price * item.stock, 0);
    const low = allItems.filter(item => item.stock < LOW_STOCK).length;

    document.getElementById("statItems").textContent = allItems.length;
    document.getElementById("statUnits").textContent = units;
    document.getElementById("statValue").textContent = money(value);
    document.getElementById("statLow").textContent = low;
}

function renderItems() {
    const search = itemSearch.value.trim().toLowerCase();
    const filter = stockFilter.value;

    const visibleItems = allItems.filter(item => {
        const name = (item.product.product_name || "").toLowerCase();
        const brand = (item.product.brands || "").toLowerCase();
        const matchesSearch = !search || name.includes(search) || brand.includes(search);
        const matchesStock =
            filter === "All" ||
            (filter === "Low" && item.stock < LOW_STOCK) ||
            (filter === "Out" && item.stock === 0);
        return matchesSearch && matchesStock;
    });

    if (visibleItems.length === 0) {
        itemList.innerHTML = "<p>No items match this search.</p>";
        return;
    }

    itemList.innerHTML = visibleItems.map(item => {
        const p = item.product;
        const stockBadge = item.stock === 0
            ? '<span class="badge badge-danger">Out of stock</span>'
            : item.stock < LOW_STOCK
                ? '<span class="badge badge-warn">Low stock</span>'
                : "";
        const nutri = p.nutriscore_grade
            ? `<span class="badge">Nutri-Score ${escapeHtml(p.nutriscore_grade.toUpperCase())}</span>`
            : "";

        return `
        <div class="item-card">
            <h4>#${item.id} — ${escapeHtml(p.product_name)}</h4>
            <div class="item-meta">
                <span class="badge">${escapeHtml(p.brands || "No brand")}</span>
                <span class="badge">Barcode: ${escapeHtml(item.barcode || "none")}</span>
                ${p.quantity ? `<span class="badge">${escapeHtml(p.quantity)}</span>` : ""}
                ${nutri}
                ${stockBadge}
            </div>
            <p class="ingredients">Ingredients: ${escapeHtml(p.ingredients_text || "not available")}</p>
            <div class="item-edit">
                <label>Price (KES)
                    <input id="price-${item.id}" type="number" step="0.01" min="0" value="${item.price}">
                </label>
                <label>Stock
                    <input id="stock-${item.id}" type="number" step="1" min="0" value="${item.stock}">
                </label>
            </div>
            <div class="item-actions">
                <button class="small" onclick="saveItem(${item.id})">Save</button>
                <button class="small secondary" onclick="enrichItem(${item.id})">Enrich from API</button>
                <button class="small danger" onclick="deleteItem(${item.id})">Delete</button>
            </div>
        </div>`;
    }).join("");
}

itemSearch.addEventListener("input", renderItems);
stockFilter.addEventListener("change", renderItems);

// CREATE: POST /inventory
document.getElementById("itemForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    const { response, data } = await api("/inventory", {
        method: "POST",
        body: JSON.stringify({
            product_name: document.getElementById("addName").value,
            brands: document.getElementById("addBrand").value,
            barcode: document.getElementById("addBarcode").value,
            price: document.getElementById("addPrice").value,
            stock: document.getElementById("addStock").value,
        }),
    });

    if (!response.ok) {
        showNotice(data.error || "Could not add item", false);
        return;
    }

    event.target.reset();
    showNotice(data.warning ? `Item added, but: ${data.warning}` : "Item added", !data.warning);
    await loadItems();
});

// UPDATE: PATCH /inventory/<id>

async function saveItem(id) {
    const { response, data } = await api(`/inventory/${id}`, {
        method: "PATCH",
        body: JSON.stringify({
            price: document.getElementById(`price-${id}`).value,
            stock: document.getElementById(`stock-${id}`).value,
        }),
    });

    if (!response.ok) {
        showNotice(data.error || "Could not update item", false);
        return;
    }

    showNotice(`Item #${id} updated`);
    await loadItems();
}

// ENRICH: POST /inventory/<id>/enrich
async function enrichItem(id) {
    const { response, data } = await api(`/inventory/${id}/enrich`, { method: "POST" });

    if (!response.ok) {
        showNotice(data.error || "Could not enrich item", false);
        return;
    }

    showNotice(`Item #${id} updated with OpenFoodFacts details`);
    await loadItems();
}

// DELETE: DELETE /inventory/<id>
async function deleteItem(id) {
    if (!confirm("Delete this item?")) return;

    const { response, data } = await api(`/inventory/${id}`, { method: "DELETE" });

    if (!response.ok) {
        showNotice(data.error || "Could not delete item", false);
        return;
    }

    showNotice(`Item #${id} deleted`);
    await loadItems();
}

// FIND ON API: GET /external/search?barcode=... or ?name=...
document.getElementById("findForm").addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = document.getElementById("findMessage");
    const result = document.getElementById("findResult");
    const params = new URLSearchParams({
        barcode: document.getElementById("findBarcode").value.trim(),
        name: document.getElementById("findName").value.trim(),
    });

    message.textContent = "Searching...";
    message.style.color = "#687684";
    result.innerHTML = "";

    const { response, data } = await api(`/external/search?${params}`);

    if (!response.ok) {
        message.textContent = data.error || "Search failed";
        message.style.color = "#b42318";
        lastFound = null;
        return;
    }

    lastFound = data;
    const p = data.product;
    message.textContent = "";
    result.innerHTML = `
        <div class="item-card">
            <h4>${escapeHtml(p.product_name || "Unnamed product")}</h4>
            <div class="item-meta">
                <span class="badge">${escapeHtml(p.brands || "No brand")}</span>
                <span class="badge">Barcode: ${escapeHtml(data.barcode || "unknown")}</span>
                ${p.quantity ? `<span class="badge">${escapeHtml(p.quantity)}</span>` : ""}
            </div>
            <p class="ingredients">Ingredients: ${escapeHtml(p.ingredients_text || "not available")}</p>
            <button class="small" onclick="useFoundProduct()">Use in Add Item form</button>
        </div>`;
});

function useFoundProduct() {
    if (!lastFound) return;

    document.getElementById("addName").value = lastFound.product.product_name || "";
    document.getElementById("addBrand").value = lastFound.product.brands || "";
    document.getElementById("addBarcode").value = lastFound.barcode || "";
    document.getElementById("addPrice").focus();
    showNotice("Form filled. Enter a price and stock, then press Add Item.");
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

checkLogin();