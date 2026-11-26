import { useState, useEffect } from "react";
import { ChevronRight, Sun, Moon, Bell, Volume2, LogOut } from "lucide-react";
import { apiRequest } from "../services/api";
import { saveTheme } from "../services/theme";
import ConfirmationDialog from "../components/ConfirmationDialog";
import "./Settings.css";

function Settings({ onOpenProfile, onLogout }) {
  const [account, setAccount] = useState(null);
  const [settings, setSettings] = useState(null);
  const [blocked, setBlocked] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showLogout, setShowLogout] = useState(false);
  useEffect(() => {
    let active = true;
    Promise.all([apiRequest("/users/me"), apiRequest("/users/me/settings"), apiRequest("/users/me/blocked")])
      .then(([account, preferences, blocked]) => { if (active) { setAccount(account); setSettings(preferences); setBlocked(blocked.users); saveTheme(preferences.theme); } })
      .catch((error) => { if (active) setError(error.message); });
    return () => { active = false; };
  }, []);
  const update = async (patch) => {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const updated = await apiRequest("/users/me/settings", { method: "PUT", body: patch });
      setSettings(updated); saveTheme(updated.theme);
      window.dispatchEvent(new Event("settings-changed"));
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  };
  const enableNotifications = () => {
    if (!settings.message_notifications && typeof Notification !== "undefined" && Notification.permission === "default") {
      Notification.requestPermission().catch(() => {});
    }
    update({ message_notifications: !settings.message_notifications });
  };
  return <main className="settings-page">
    <header className="settings-header"><h1>Settings</h1><p>Manage your account and preferences.</p></header>
    {error && <p className="auth-error" role="alert">{error}</p>}
    <div className="settings-content">
      <section className="settings-section"><h2>Account</h2><button className="settings-card settings-account-card" onClick={onOpenProfile}><div className="settings-row-info">{account ? <><h3>{account.name}</h3><p>@{account.username}</p></> : <p>Loading account...</p>}</div><ChevronRight size={20} /></button></section>
      {settings ? <>
        <section className="settings-section"><h2>Appearance</h2><div className="settings-card">
          <div className="settings-row"><Moon size={19} /><div className="settings-row-info"><h3>Theme</h3><p>Choose how ChatApp looks</p></div></div>
          <div className="settings-theme-options">{["light", "dark"].map((theme) => <button key={theme} disabled={busy} className={`settings-theme-option ${settings.theme === theme ? "selected" : ""}`} aria-pressed={settings.theme === theme} onClick={() => update({ theme })}>{theme === "light" ? <Sun size={17} /> : <Moon size={17} />}{theme === "light" ? "Light" : "Dark"}</button>)}</div>
        </div></section>
        <section className="settings-section"><h2>Notifications</h2><div className="settings-card">
          <div className="settings-row"><Bell size={19} /><div className="settings-row-info"><h3>Message notifications</h3><p>Alert when a new message arrives while this app is in the background.</p></div><button disabled={busy} role="switch" aria-label="Message notifications" aria-checked={settings.message_notifications} className={`settings-switch ${settings.message_notifications ? "enabled" : ""}`} onClick={enableNotifications}><span /></button></div>
          <div className="settings-row"><Volume2 size={19} /><div className="settings-row-info"><h3>Sound</h3><p>Play a sound for background message alerts after you interact with the app.</p></div><button disabled={busy} role="switch" aria-label="Notification sound" aria-checked={settings.sound_enabled} className={`settings-switch ${settings.sound_enabled ? "enabled" : ""}`} onClick={() => update({ sound_enabled: !settings.sound_enabled })}><span /></button></div>
        </div></section>
      </> : !error && <p role="status">Loading settings...</p>}
      <section className="settings-section"><h2>Blocked users</h2><div className="settings-card">{blocked.length ? blocked.map((person) => <div className="settings-row" key={person.user_id}><div className="settings-row-info"><h3>{person.name}</h3><p>@{person.username}</p></div><button disabled={busy} className="profile-button" onClick={async () => {
        setBusy(true); setError("");
        try { await apiRequest(`/users/me/blocked/${person.user_id}`, { method: "DELETE" }); setBlocked((previous) => previous.filter((item) => item.user_id !== person.user_id)); }
        catch (error) { setError(error.message); }
        finally { setBusy(false); }
      }}>Unblock</button></div>) : <p>No blocked users. You can block someone from their conversation.</p>}</div></section>
      <section className="settings-section settings-logout-section"><button className="settings-logout-button" onClick={() => setShowLogout(true)}><LogOut size={18} />Log out</button></section>
    </div>
    {showLogout && <ConfirmationDialog title="Log out of ChatApp?" description="You will need to log in again to access your conversations." cancelLabel="Cancel" confirmLabel="Log out" danger onCancel={() => setShowLogout(false)} onConfirm={() => { setShowLogout(false); onLogout(); }} />}
  </main>;
}
export default Settings;
