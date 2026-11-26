import { useState, useRef, useEffect, useCallback, lazy, Suspense } from "react";
import { Paperclip, Smile, Send, MessageCircle, Pencil, Trash2, Reply } from "lucide-react";
import { apiRequest, API_BASE_URL } from "../services/api";
const EmojiPicker = lazy(() => import("emoji-picker-react"));
import ConfirmationDialog from "./ConfirmationDialog";
import "./ChatWorkspace.css";

function ChatWorkspace({ chats, selectedChat, currentUserId, onChatChanged, onBack }) {
  const chat = chats.find((item) => item.id === selectedChat);
  const [messages, setMessages] = useState([]);
  const [messageText, setMessageText] = useState("");
  const [emoji, setEmoji] = useState(false);
  const [file, setFile] = useState(null);
  const [reply, setReply] = useState(null);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [loading, setLoading] = useState(Boolean(selectedChat));
  const [hasMore, setHasMore] = useState(false);
  const revision = useRef(0);
  const busy = useRef(false);
  const alive = useRef(false);
  const end = useRef(null);
  const fileInput = useRef(null);
  const previousLast = useRef(null);
  const messagesRef = useRef([]);
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  const refresh = useCallback(async () => {
    if (!selectedChat) return;
    const version = revision.current;
    const oldest = messagesRef.current[0]?.message_id;
    let data = await apiRequest(`/chats/${selectedChat}/messages?limit=100`);
    let rows = data.messages;
    while (oldest && data.has_more && rows[0]?.message_id > oldest && alive.current && version === revision.current) {
      data = await apiRequest(`/chats/${selectedChat}/messages?limit=100&before=${rows[0].message_id}`);
      rows = [...data.messages, ...rows];
    }
    if (!alive.current || version !== revision.current) return;
    setMessages(oldest ? rows.filter((item) => item.message_id >= oldest) : rows);
    setHasMore(data.has_more || Boolean(oldest && rows.some((item) => item.message_id < oldest)));
    setLoading(false);
    const latest = rows.at(-1);
    if (latest && document.visibilityState === "visible") {
      await apiRequest(`/chats/${selectedChat}/read`, { method: "POST", body: { message_id: latest.message_id } });
    }
  }, [selectedChat]);

  useEffect(() => {
    alive.current = true;
    let timer;
    const poll = async () => {
      try { if (!busy.current) await refresh(); }
      catch (error) { if (alive.current) { setError(error.message); setLoading(false); } }
      if (alive.current) timer = setTimeout(poll, 2500);
    };
    poll();
    return () => { alive.current = false; revision.current += 1; clearTimeout(timer); };
  }, [refresh]);
  useEffect(() => {
    const latest = messages.at(-1)?.message_id;
    if (latest && latest !== previousLast.current) end.current?.scrollIntoView({ behavior: "smooth" });
    previousLast.current = latest;
  }, [messages]);

  const mutate = async (operation) => {
    if (busy.current) return;
    busy.current = true; revision.current += 1; setPending(true); setError("");
    try {
      await operation();
      revision.current += 1;
      if (!alive.current) return;
      await refresh();
      await onChatChanged();
    } catch (error) { if (alive.current) setError(error.message); }
    finally { busy.current = false; if (alive.current) setPending(false); }
  };
  const send = () => {
    if ((!messageText.trim() && !file) || chat?.blocked) return;
    mutate(async () => {
      if (editing) {
        await apiRequest(`/messages/${editing.message_id}`, { method: "PUT", body: { content: messageText.trim() } });
      } else {
        let attachmentId = null;
        if (file) {
          const form = new FormData(); form.append("file", file);
          const upload = await apiRequest(`/chats/${selectedChat}/attachments`, { method: "POST", body: form });
          attachmentId = upload.attachment_id;
        }
        await apiRequest(`/chats/${selectedChat}/messages`, { method: "POST", body: { content: messageText.trim(), reply_to_message_id: reply?.message_id ?? null, attachment_id: attachmentId } });
      }
      if (alive.current) {
        setMessageText(""); setReply(null); setEditing(null); setFile(null);
        if (fileInput.current) fileInput.current.value = "";
      }
    });
  };
  const loadOlder = async () => {
    if (busy.current || !messages.length) return;
    busy.current = true; revision.current += 1; setPending(true);
    try {
      const data = await apiRequest(`/chats/${selectedChat}/messages?limit=100&before=${messages[0].message_id}`);
      if (alive.current) { setMessages((previous) => [...data.messages, ...previous]); setHasMore(data.has_more); }
    } catch (error) { if (alive.current) setError(error.message); }
    finally { busy.current = false; if (alive.current) setPending(false); }
  };

  if (!chat) return <main className="chat-workspace"><div className="empty-chat"><MessageCircle size={30} /><h3>Select a conversation</h3><p>Add a contact using the + button to start chatting.</p></div></main>;
  return <main className="chat-workspace">
    <header className="workspace-header">
      <button className="chat-back-button profile-button" onClick={onBack}>Back</button>
      <div className="workspace-user"><div className={`workspace-avatar ${chat.avatarColor}`}>{chat.avatar}</div><div className="workspace-user-info"><h2>{chat.name}</h2><span>{chat.blocked ? "Conversation blocked" : "Conversation"}</span></div></div>
      <button className="profile-button" disabled={pending} onClick={() => mutate(async () => {
        await apiRequest(`/users/me/blocked/${chat.contactId}`, { method: chat.blockedByMe ? "DELETE" : "PUT" });
      })}>{chat.blockedByMe ? "Unblock contact" : "Block contact"}</button>
    </header>
    {error && <p className="auth-error" role="alert">{error}</p>}
    <section className="messages-area">
      {hasMore && <button className="profile-button" disabled={pending} onClick={loadOlder}>Load older messages</button>}
      <div className="messages-list">
        {loading ? <p role="status">Loading messages...</p> : messages.length === 0 ? <div className="empty-chat"><h3>No messages yet</h3><p>Say hello to {chat.name}.</p></div> : messages.map((message) => {
          const outgoing = message.sender_id === currentUserId;
          const original = messages.find((item) => item.message_id === message.reply_to_message_id);
          return <div className={`message-row ${outgoing ? "outgoing" : "incoming"}`} key={message.message_id}>
            <div className="message-group">
              <div className="message-bubble">
                {message.reply_to_message_id && <div className="message-reply-quote">{original?.content || "Earlier message"}</div>}
                <div className="message-content">{message.content}</div>
                {message.attachment_id && <a className="attachment-download" href={`${API_BASE_URL}/attachments/${message.attachment_id}`} download>Download attachment</a>}
              </div>
              <div className="message-time">{new Date(message.sent_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</div>
              <div className="message-tools">
                <button disabled={pending || chat.blocked} aria-label="Reply to message" onClick={() => { setReply(message); setEditing(null); }}><Reply size={14} /></button>
                {outgoing && <>
                  <button disabled={pending || chat.blocked} aria-label="Edit message" onClick={() => { setEditing(message); setMessageText(message.content); setReply(null); setFile(null); }}><Pencil size={14} /></button>
                  <button disabled={pending} aria-label="Delete message" onClick={() => setDeleting(message)}><Trash2 size={14} /></button>
                </>}
              </div>
            </div>
          </div>;
        })}
        <div ref={end} />
      </div>
    </section>
    <div className="composer-area">
      {chat.blocked && <p role="status">Messages cannot be sent while either participant has blocked the other.</p>}
      {file && <div className="selected-file"><span>{file.name}</span><button disabled={pending} onClick={() => { setFile(null); if (fileInput.current) fileInput.current.value = ""; }}>Remove attachment</button></div>}
      {(reply || editing) && <div className="reply-preview"><span>{editing ? "Editing" : "Replying to"}: {(editing || reply).content}</span><button disabled={pending} onClick={() => { setReply(null); setEditing(null); setMessageText(""); }}>Cancel</button></div>}
      {emoji && <Suspense fallback={<p role="status">Loading emoji picker...</p>}><EmojiPicker theme={document.documentElement.dataset.theme === "dark" ? "dark" : "light"} onEmojiClick={(item) => { setMessageText((previous) => previous + item.emoji); setEmoji(false); }} /></Suspense>}
      <input ref={fileInput} type="file" hidden onChange={(event) => {
        const selected = event.target.files?.[0];
        if (selected?.size > 5 * 1024 * 1024) { setError("Attachments must be at most 5 MB."); event.target.value = ""; return; }
        setFile(selected || null);
      }} />
      <div className="message-composer">
        <button className="composer-action" disabled={pending || Boolean(editing) || chat.blocked} aria-label="Attach file" onClick={() => fileInput.current?.click()}><Paperclip size={20} /></button>
        <input aria-label="Message" placeholder="Type a message..." maxLength={10000} disabled={pending || chat.blocked} value={messageText} onChange={(event) => setMessageText(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); send(); } }} />
        <button className="composer-action" disabled={pending || chat.blocked} aria-label="Emoji" onClick={() => setEmoji((previous) => !previous)}><Smile size={20} /></button>
        <button className="send-button" disabled={pending || chat.blocked || (!messageText.trim() && !file)} aria-label={editing ? "Save message" : "Send message"} onClick={send}><Send size={19} /></button>
      </div>
    </div>
    {deleting && <ConfirmationDialog title="Delete message?" description="This deletes the message for both participants." confirmLabel="Delete" cancelLabel="Cancel" danger onCancel={() => setDeleting(null)} onConfirm={() => {
      const id = deleting.message_id; setDeleting(null);
      mutate(async () => {
        await apiRequest(`/messages/${id}`, { method: "DELETE" });
        if (alive.current) { setMessages((previous) => previous.filter((item) => item.message_id !== id)); if (editing?.message_id === id) { setEditing(null); setMessageText(""); } }
      });
    }} />}
  </main>;
}
export default ChatWorkspace;
