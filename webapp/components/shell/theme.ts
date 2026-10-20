// components/shell/theme.ts -- the ONE theme system for both route groups.
// html[data-theme] drives analytics.css and the shell; html.dark drives the terminal's
// globals.css + tailwind (darkMode: class). One key, "cv-theme"; the old analytics key
// is read once as a fallback; with no stored choice the OS preference wins.

export const THEME_KEY = "cv-theme";

export const THEME_INIT_SCRIPT = `(function(){var r=document.documentElement,t=null;try{t=localStorage.getItem('cv-theme')||localStorage.getItem('cv-analytics-theme');}catch(e){}var d=t?t==='dark':!!(window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches);r.classList.toggle('dark',d);r.setAttribute('data-theme',d?'dark':'light');})();`;

export function applyTheme(dark: boolean): void {
  const r = document.documentElement;
  r.classList.toggle("dark", dark);
  r.setAttribute("data-theme", dark ? "dark" : "light");
  try {
    localStorage.setItem(THEME_KEY, dark ? "dark" : "light");
  } catch {
    /* private mode: the choice lasts for this page only */
  }
}
