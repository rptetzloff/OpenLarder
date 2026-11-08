// Light, dark, or whatever the device says (Ray, 2026-11-08). The page's
// colours follow <html data-theme>, which is always "light" or "dark":
// index.html sets it before anything is drawn, and this keeps it in step.
// The choice is this browser's alone, kept in localStorage.

export type ThemeChoice = "system" | "light" | "dark";

const KEY = "openlarder_theme";
const darkDevice = window.matchMedia("(prefers-color-scheme: dark)");

export function savedTheme(): ThemeChoice {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    // Storage blocked: follow the device.
  }
  return "system";
}

function apply(choice: ThemeChoice) {
  const dark = choice === "dark" || (choice === "system" && darkDevice.matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function chooseTheme(choice: ThemeChoice) {
  try {
    if (choice === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, choice);
  } catch {
    // Still applies to this page, just isn't remembered.
  }
  apply(choice);
}

// Following the device means following it when it changes, too.
darkDevice.addEventListener("change", () => apply(savedTheme()));
