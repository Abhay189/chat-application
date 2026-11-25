const THEME_KEY = "chatapp-theme";

export function applyTheme(theme) {
  const selected = theme === "dark" ? "dark" : "light";
  document.documentElement.dataset.theme = selected;
  return selected;
}

export function initializeTheme() {
  let theme = "light";
  try {
    theme = localStorage.getItem(THEME_KEY);
  } catch {
    // Theme switching still works when browser storage is unavailable.
  }
  return applyTheme(theme);
}

export function saveTheme(theme) {
  const selected = applyTheme(theme);
  try {
    localStorage.setItem(THEME_KEY, selected);
  } catch {
    // Keep the selected theme for the current session.
  }
  return selected;
}
