import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "@/app/App";
import "@/app/styles/design-system.css";
import "@/app/styles/styles.css";

async function clearLocalServiceWorkers() {
  if (
    !("serviceWorker" in navigator) ||
    (window.location.hostname !== "localhost" && window.location.hostname !== "127.0.0.1")
  ) {
    return true;
  }

  const registrations = await navigator.serviceWorker.getRegistrations();
  await Promise.all(registrations.map((registration) => registration.unregister()));

  if (navigator.serviceWorker.controller && registrations.length > 0 && !sessionStorage.getItem("kg-sw-cleaned")) {
    sessionStorage.setItem("kg-sw-cleaned", "1");
    window.location.reload();
    return false;
  }

  return true;
}

clearLocalServiceWorkers().then((shouldRender) => {
  if (!shouldRender) {
    return;
  }

  ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
});
