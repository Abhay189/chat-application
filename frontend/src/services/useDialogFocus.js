import { useEffect } from "react";

export function useDialogFocus(ref) {
  useEffect(() => {
    const previous = document.activeElement;
    const dialog = ref.current;
    const selector = 'button:not(:disabled), input:not(:disabled), a[href], textarea:not(:disabled), select:not(:disabled), [tabindex="0"]';
    const elements = () => [...dialog.querySelectorAll(selector)].filter((element) => element.getClientRects().length);
    elements()[0]?.focus();
    const trap = (event) => {
      if (event.key !== "Tab") return;
      const items = elements();
      const first = items[0]; const last = items.at(-1);
      if (!first) { event.preventDefault(); return; }
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", trap);
    return () => { document.removeEventListener("keydown", trap); if (previous?.isConnected) previous.focus(); };
  }, [ref]);
}
