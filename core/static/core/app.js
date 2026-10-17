const saleForm = document.querySelector("[data-sale-form]");

if (saleForm) {
  const search = document.querySelector("[data-product-search]");
  const cards = [...document.querySelectorAll("[data-add-product]")];
  const categoryButtons = [...document.querySelectorAll("[data-category-filter]")];
  const noResults = document.querySelector("[data-no-results]");
  const cartLines = document.querySelector("[data-sale-lines]");
  const hiddenInputs = document.querySelector("[data-sale-hidden]");
  const emptyCart = document.querySelector("[data-sale-empty]");
  const totalElement = document.querySelector("[data-sale-total]");
  const cartCount = document.querySelector("[data-cart-count]");
  const checkout = document.querySelector("[data-checkout]");
  const adHocPanel = document.querySelector("[data-adhoc-panel]");
  const adHocName = document.querySelector("[data-adhoc-name]");
  const adHocPrice = document.querySelector("[data-adhoc-price]");
  const adHocQuantity = document.querySelector("[data-adhoc-quantity]");
  const mobileCartBar = document.querySelector("[data-mobile-cart-bar]");
  const mobileCartCount = document.querySelector("[data-mobile-cart-count]");
  const mobileCartTotal = document.querySelector("[data-mobile-cart-total]");
  const currency = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  const cart = new Map();
  let activeCategory = "*";

  const normalize = (value) => value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  const categoryEmoji = (card) => card.dataset.categoryEmoji || "🛍️";

  function filterProducts() {
    const query = normalize(search.value.trim());
    let visibleCount = 0;
    cards.forEach((card) => {
      const category = card.dataset.category || "Outros";
      const visible = (activeCategory === "*" || category === activeCategory)
        && normalize(card.dataset.name).includes(query);
      card.hidden = !visible;
      if (visible) visibleCount += 1;
    });
    noResults.hidden = visibleCount > 0 || (activeCategory === "Outros" && query === "");
  }

  function makeButton(label, className, onClick, ariaLabel) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.textContent = label;
    if (ariaLabel) button.setAttribute("aria-label", ariaLabel);
    button.addEventListener("click", onClick);
    return button;
  }

  function appendHidden(name, value) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    hiddenInputs.append(input);
  }

  function renderCart() {
    cartLines.replaceChildren();
    hiddenInputs.replaceChildren();
    emptyCart.hidden = cart.size > 0;
    checkout.disabled = cart.size === 0;
    let subtotal = 0;
    let quantityTotal = 0;

    cart.forEach((product) => {
      subtotal += product.price * product.quantity;
      quantityTotal += product.quantity;
      const row = document.createElement("article");
      row.className = "cart-line";
      const details = document.createElement("div");
      details.className = "cart-product-details";
      const name = document.createElement("strong");
      name.textContent = `${product.emoji || product.categoryEmoji || "🛍️"} ${product.name}`;
      const unitPrice = document.createElement("small");
      unitPrice.textContent = `${currency.format(product.price)} cada${product.adHoc ? " · avulso" : ""}`;
      details.append(name, unitPrice);

      const controls = document.createElement("div");
      controls.className = "quantity-controls";
      controls.append(makeButton("−", "quantity-button", () => changeQuantity(product.id, -1), `Diminuir ${product.name}`));
      const quantity = document.createElement("span");
      quantity.textContent = product.quantity;
      controls.append(quantity);
      controls.append(makeButton("+", "quantity-button", () => changeQuantity(product.id, 1), `Aumentar ${product.name}`));

      const subtotal = document.createElement("strong");
      subtotal.className = "cart-subtotal";
      subtotal.textContent = currency.format(product.price * product.quantity);
      row.append(details, controls, subtotal);
      cartLines.append(row);

      if (product.adHoc) {
        appendHidden("avulso_descricao", product.name);
        appendHidden("avulso_preco", product.price.toFixed(2));
        appendHidden("avulso_quantidade", String(product.quantity));
      } else {
        appendHidden("itens", product.id);
        appendHidden(`quantidade_${product.id}`, String(product.quantity));
      }
    });

    const total = subtotal;
    const countText = `${quantityTotal} ${quantityTotal === 1 ? "item" : "itens"}`;
    totalElement.textContent = currency.format(total);
    cartCount.textContent = countText;
    mobileCartCount.textContent = countText;
    mobileCartTotal.textContent = currency.format(total);
    mobileCartBar.hidden = cart.size === 0;
  }

  function changeQuantity(id, delta) {
    const product = cart.get(id);
    if (!product) return;
    const next = product.quantity + delta;
    if (next <= 0) cart.delete(id);
    else if (next <= product.stock) product.quantity = next;
    else return;
    renderCart();
  }

  search.addEventListener("input", filterProducts);
  search.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    cards.find((card) => !card.hidden && !card.disabled)?.click();
  });

  categoryButtons.forEach((button) => {
    button.addEventListener("click", () => {
      activeCategory = button.dataset.categoryFilter;
      categoryButtons.forEach((tab) => tab.classList.toggle("active", tab === button));
      adHocPanel.hidden = activeCategory !== "Outros";
      filterProducts();
    });
  });

  cards.forEach((card) => {
    const emoji = card.querySelector(".product-emoji");
    emoji.textContent = card.dataset.emoji || categoryEmoji(card);
    card.addEventListener("click", () => {
      if (card.disabled) return;
      const id = card.dataset.id;
      const existing = cart.get(id);
      const nextQuantity = (existing?.quantity || 0) + 1;
      if (nextQuantity > Number(card.dataset.stock)) return;
      cart.set(id, {
        id,
        name: card.dataset.name,
        category: card.dataset.category || "Outros",
        categoryEmoji: categoryEmoji(card),
        emoji: card.dataset.emoji,
        price: Number(card.dataset.price.replace(",", ".")),
        stock: Number(card.dataset.stock),
        quantity: nextQuantity,
      });
      renderCart();
    });
  });

  document.querySelector("[data-add-adhoc]")?.addEventListener("click", () => {
    const name = adHocName.value.trim();
    const price = Number(adHocPrice.value.replace(",", "."));
    const quantity = Number(adHocQuantity.value);
    if (!name || !Number.isFinite(price) || price <= 0 || !Number.isInteger(quantity) || quantity < 1) {
      adHocName.setCustomValidity("Informe descrição, preço maior que zero e quantidade válida.");
      adHocName.reportValidity();
      adHocName.setCustomValidity("");
      return;
    }
    const id = `avulso-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    cart.set(id, { id, name, category: "Outros", categoryEmoji: "🧺", price, quantity, stock: Number.POSITIVE_INFINITY, adHoc: true });
    adHocName.value = "";
    adHocPrice.value = "";
    adHocQuantity.value = "1";
    renderCart();
  });

  [adHocName, adHocPrice, adHocQuantity].forEach((input) => {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        document.querySelector("[data-add-adhoc]").click();
      }
    });
  });

  mobileCartBar.addEventListener("click", () => {
    document.querySelector("#sale-cart").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  saleForm.addEventListener("submit", (event) => {
    if (cart.size === 0) {
      event.preventDefault();
      return;
    }
    if (!saleForm.checkValidity()) {
      event.preventDefault();
      saleForm.reportValidity();
      return;
    }
    checkout.disabled = true;
    checkout.textContent = "Registrando venda…";
  });

  renderCart();
}
