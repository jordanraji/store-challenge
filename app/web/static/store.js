document.addEventListener("htmx:beforeSwap", (event) => {
  if ([409, 422].includes(event.detail.xhr.status)) {
    event.detail.shouldSwap = true;
    event.detail.isError = false;
  }
});
document.addEventListener("htmx:afterRequest", (event) => {
  if (event.detail.failed && ![409, 422].includes(event.detail.xhr.status)) {
    const notice = document.querySelector("#notification");
    if (notice) {
      notice.textContent = "The request could not be completed. Check your connection and try again.";
      notice.className = "notification is-visible is-error";
    }
  }
});
document.addEventListener("submit", (event) => {
  if (event.target.matches("[data-checkout]")) {
    if (event.target.dataset.submitting) { event.preventDefault(); return; }
    event.target.dataset.submitting = "true";
    const button = event.target.querySelector("button");
    button.disabled = true;
    button.textContent = "Placing your order…";
  }
});
window.addEventListener("pageshow", () => {
  document.querySelectorAll("[data-checkout][data-submitting]").forEach((form) => {
    delete form.dataset.submitting;
    const button = form.querySelector("button");
    button.disabled = false;
    button.textContent = "Place order";
  });
});
