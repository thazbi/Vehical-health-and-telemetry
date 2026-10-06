const sidebar = document.querySelector("#sidebar");
const menuToggle = document.querySelector("#menu-toggle");
const searchInput = document.querySelector("#guide-search");
const toc = document.querySelector("#toc");
const toast = document.querySelector("#toast");
const navLinks = [...document.querySelectorAll(".toc-link")];
let toastTimer;

const emptyResult = document.createElement("p");
emptyResult.className = "search-empty";
emptyResult.textContent = "No sections match that search.";
toc.append(emptyResult);

function setActiveLink(id) {
  navLinks.forEach((link) => {
    const isActive = link.hash === `#${id}`;
    link.classList.toggle("is-active", isActive);
    if (isActive) link.setAttribute("aria-current", "location");
    else link.removeAttribute("aria-current");
  });
}

function closeMenu() {
  sidebar.classList.remove("is-open");
  menuToggle.setAttribute("aria-expanded", "false");
  menuToggle.setAttribute("aria-label", "Open guide navigation");
}

menuToggle.addEventListener("click", () => {
  const isOpen = sidebar.classList.toggle("is-open");
  menuToggle.setAttribute("aria-expanded", String(isOpen));
  menuToggle.setAttribute("aria-label", isOpen ? "Close guide navigation" : "Open guide navigation");
});

navLinks.forEach((link) => link.addEventListener("click", () => closeMenu()));

document.addEventListener("keydown", (event) => {
  if (event.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) {
    event.preventDefault();
    searchInput.focus();
  }
  if (event.key === "Escape") {
    if (document.activeElement === searchInput) {
      searchInput.value = "";
      searchInput.dispatchEvent(new Event("input"));
      searchInput.blur();
    }
    closeMenu();
  }
});

searchInput.addEventListener("input", () => {
  const query = searchInput.value.trim().toLowerCase();
  let firstMatch = null;
  navLinks.forEach((link) => {
    const searchable = `${link.textContent} ${link.dataset.search}`.toLowerCase();
    const matches = !query || searchable.includes(query);
    link.hidden = !matches;
    if (matches && !firstMatch) firstMatch = link;
  });
  emptyResult.style.display = firstMatch ? "none" : "block";
  if (query && firstMatch) setActiveLink(firstMatch.hash.slice(1));
});

searchInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    const match = navLinks.find((link) => !link.hidden);
    if (match) {
      match.click();
      window.location.hash = match.hash;
      searchInput.blur();
    }
  }
});

const sections = [...document.querySelectorAll(".section-anchor")];
if ("IntersectionObserver" in window) {
  const observer = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((first, second) => second.intersectionRatio - first.intersectionRatio)[0];
    if (visible) setActiveLink(visible.target.id);
  }, { rootMargin: "-18% 0px -68% 0px", threshold: [0, 0.1, 0.35] });
  sections.forEach((section) => observer.observe(section));
}

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const temporary = document.createElement("textarea");
  temporary.value = text;
  temporary.setAttribute("readonly", "");
  temporary.style.position = "fixed";
  temporary.style.opacity = "0";
  document.body.append(temporary);
  temporary.select();
  const copied = document.execCommand("copy");
  temporary.remove();
  if (!copied) throw new Error("Clipboard permission was not available.");
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("is-visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 1900);
}

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.addEventListener("click", async () => {
    const target = document.getElementById(button.dataset.copy);
    if (!target) return;
    try {
      await copyText(target.textContent.trim());
      button.classList.add("is-copied");
      button.innerHTML = 'Copied <span aria-hidden="true">✓</span>';
      showToast("Commands copied to clipboard");
      window.setTimeout(() => {
        button.classList.remove("is-copied");
        button.innerHTML = 'Copy <span aria-hidden="true">⧉</span>';
      }, 1500);
    } catch {
      showToast("Copy was blocked by the browser");
    }
  });
});
