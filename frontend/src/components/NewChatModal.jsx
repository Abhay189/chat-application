import { useState, useEffect, useRef } from "react";
import { Search, Plus, X, MessageCircle, Trash2 } from "lucide-react";
import { useDialogFocus } from "../services/useDialogFocus";
import { apiRequest } from "../services/api";
import "./NewChatModal.css";

function NewChatModal({ onClose, onSelectContact }) {
  const dialogRef = useRef(null);
  useDialogFocus(dialogRef);
  const [query, setQuery] = useState("");
  const [contacts, setContacts] = useState([]);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    apiRequest("/contacts").then((data) => { if (active) setContacts(data.contacts); })
      .catch((error) => { if (active) setError(error.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (query.trim().length < 2) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      apiRequest(`/users?q=${encodeURIComponent(query.trim())}`, { signal: controller.signal })
        .then((data) => { if (!controller.signal.aborted) setResults(data.users); })
        .catch((error) => { if (error.name !== "AbortError") setError(error.message); });
    }, 250);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [query]);
  useEffect(() => {
    const close = (event) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", close);
    return () => document.removeEventListener("keydown", close);
  }, [onClose]);
  const action = async (user, operation) => {
    setBusy(user.user_id); setError("");
    try {
      if (operation === "add") {
        await apiRequest("/contacts", { method: "POST", body: { user_id: user.user_id } });
        setContacts((previous) => [...previous.filter((item) => item.user_id !== user.user_id), { ...user, is_contact: true }]);
      } else if (operation === "remove") {
        await apiRequest(`/contacts/${user.user_id}`, { method: "DELETE" });
        setContacts((previous) => previous.filter((item) => item.user_id !== user.user_id));
        setResults((previous) => previous.map((item) => item.user_id === user.user_id ? { ...item, is_contact: false } : item));
      } else await onSelectContact(user);
    } catch (error) { setError(error.message); }
    finally { setBusy(null); }
  };
  const searching = query.trim().length >= 2;
  const people = searching ? results : contacts;
  return <div className="new-chat-overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section ref={dialogRef} className="new-chat-modal" role="dialog" aria-modal="true" aria-labelledby="new-chat-title">
      <div className="new-chat-header"><h2 id="new-chat-title">Contacts</h2><button className="new-chat-close" onClick={onClose} aria-label="Close contacts"><X size={18} /></button></div>
      <div className="new-chat-search"><Search size={17} /><input autoFocus aria-label="Search by username or email" placeholder="Search by username or email" value={query} onChange={(event) => { setQuery(event.target.value); setResults([]); setError(""); }} /></div>
      <p className="new-chat-empty">{searching ? "Search results" : "Your saved contacts. Search to add someone (at least 2 characters)."}</p>
      {error && <p className="auth-error" role="alert">{error}</p>}
      <div className="new-chat-people">
        {loading ? <p role="status">Loading contacts...</p> : people.length ? people.map((person) => {
          const saved = contacts.some((item) => item.user_id === person.user_id);
          return <div className="new-chat-person" key={person.user_id}>
            <div className="new-chat-avatar">{person.name.charAt(0).toUpperCase()}</div>
            <div className="new-chat-person-info"><span>{person.name}</span><small>@{person.username}</small><small>{person.email}</small></div>
            {saved ? <>
              <button className="new-chat-add" disabled={busy !== null} aria-label={`Chat with ${person.name}`} onClick={() => action(person, "chat")}><MessageCircle size={18} /></button>
              <button className="new-chat-add" disabled={busy !== null} aria-label={`Remove ${person.name} from contacts`} onClick={() => action(person, "remove")}><Trash2 size={18} /></button>
            </> : <button className="new-chat-add" disabled={busy !== null} aria-label={`Add ${person.name} to contacts`} onClick={() => action(person, "add")}><Plus size={18} /></button>}
          </div>;
        }) : <p className="new-chat-empty">{searching ? "No matching users found." : "No contacts yet."}</p>}
      </div>
    </section>
  </div>;
}
export default NewChatModal;
