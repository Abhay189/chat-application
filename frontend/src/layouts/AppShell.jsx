import { useState, useEffect, useCallback, useRef } from "react";
import { apiRequest } from "../services/api";
import { saveTheme } from "../services/theme";
import ChatSidebar from "../components/ChatSidebar";
import ChatWorkspace from "../components/ChatWorkspace";
import NavigationRail from "../components/NavigationRail";
import Profile from "../pages/Profile";
import SettingsPage from "../pages/Settings";
import Login from "../pages/Login";
import Register from "../pages/Register";
import "./AppShell.css";

function AppShell() {
  const [user, setUser] = useState(null);
  const [restoring, setRestoring] = useState(true);
  const [selectedChat, setSelectedChat] = useState(null);
  const [chatData, setChatData] = useState([]);
  const [activeView, setActiveView] = useState("home");
  const [authView, setAuthView] = useState("login");
  const [error, setError] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  const seenMessages = useRef(new Map());
  const preferences = useRef(null);
  const audio = useRef(null);
  const userId = user?.user_id;

  const clearSession = useCallback(() => {
    setUser(null);
    setChatData([]);
    setSelectedChat(null);
    setActiveView("home");
    setAuthView("login");
    seenMessages.current.clear();
    preferences.current = null;
    document.title = "ChatApp";
  }, []);

  useEffect(() => {
    let active = true;
    apiRequest("/users/me").then((user) => { if (active) setUser(user); })
      .catch((error) => { if (active && error.status !== 401) setError(error.message); })
      .finally(() => { if (active) setRestoring(false); });
    window.addEventListener("session-ended", clearSession);
    return () => { active = false; window.removeEventListener("session-ended", clearSession); };
  }, [clearSession]);

  useEffect(() => {
    if (!userId) return;
    let active = true;
    const load = () => apiRequest("/users/me/settings").then((settings) => {
      if (!active) return;
      preferences.current = settings;
      saveTheme(settings.theme);
    }).catch((error) => { if (active) setError(error.message); });
    load();
    window.addEventListener("settings-changed", load);
    return () => { active = false; window.removeEventListener("settings-changed", load); };
  }, [userId]);

  useEffect(() => {
    const updated = () => apiRequest("/users/me").then(setUser).catch((error) => setError(error.message));
    const enableAudio = () => {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext && !audio.current) audio.current = new AudioContext();
      audio.current?.resume().catch(() => {});
    };
    window.addEventListener("profile-changed", updated);
    window.addEventListener("pointerdown", enableAudio);
    return () => { window.removeEventListener("profile-changed", updated); window.removeEventListener("pointerdown", enableAudio); };
  }, []);

  const notify = useCallback((chat) => {
    const settings = preferences.current;
    if (!settings?.message_notifications || !document.hidden) return;
    document.title = `New message from ${chat.other_user.name} - ChatApp`;
    if (typeof Notification !== "undefined" && Notification.permission === "granted") {
      new Notification(`New message from ${chat.other_user.name}`, { body: "Open ChatApp to read it." });
    }
    const context = audio.current;
    if (settings.sound_enabled && context?.state === "running") {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      gain.gain.value = 0.08;
      oscillator.frequency.value = 660;
      oscillator.connect(gain).connect(context.destination);
      oscillator.start(); oscillator.stop(context.currentTime + 0.15);
    }
  }, []);

  const fetchChats = useCallback(async (isActive = () => true) => {
    const data = await apiRequest("/chats");
    if (!isActive()) return;
    for (const chat of data.chats) {
      const latest = chat.latest_message;
      const previous = seenMessages.current.get(chat.chat_id);
      if (latest && previous !== undefined && latest.message_id > previous && latest.sender_id !== userId) notify(chat);
      seenMessages.current.set(chat.chat_id, latest?.message_id || 0);
    }
    setChatData((previous) => data.chats.map((chat) => {
      const old = previous.find((item) => item.id === chat.chat_id);
      const name = chat.other_user.name || chat.other_user.username;
      const latest = chat.latest_message;
      
      return {
        id: chat.chat_id, contactId: chat.other_user.user_id, name, blocked: chat.blocked, blockedByMe: chat.blocked_by_me,
        message: latest?.content || "No messages yet.", latestId: latest?.message_id,
        time: latest ? new Date(latest.sent_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "",
        unread: chat.chat_id === selectedChat ? 0 : chat.unread,
        avatar: name.charAt(0).toUpperCase(), avatarColor: "avatar-olive", messages: old?.messages || [],
      };
    }));
  }, [userId, selectedChat, notify]);

  useEffect(() => {
    if (!userId) return;
    let active = true;
    let timer;
    const poll = async () => {
      try { await fetchChats(() => active); }
      catch (error) { if (active) setError(error.message); }
      if (active) timer = setTimeout(poll, 4000);
    };
    poll();
    return () => { active = false; clearTimeout(timer); };
  }, [userId, fetchChats]);

  const handleNewChat = async (contact) => {
    const result = await apiRequest("/chats", { method: "POST", body: { user_id: contact.user_id } });
    await fetchChats();
    setSelectedChat(result.chat_id);
    setActiveView("chats");
  };
  const handleLogin = (loginData) => {
    setError(""); setUser(loginData); setActiveView("home");
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext && !audio.current) audio.current = new AudioContext();
    audio.current?.resume().catch(() => {});
  };
  const handleLogout = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    try { await apiRequest("/users/logout", { method: "POST" }); clearSession(); setError(""); }
    catch (error) { if (error.status !== 401) setError(`Logout failed: ${error.message} Please try again.`); }
    finally { setLoggingOut(false); }
  };

  if (restoring) return <main className="auth-page"><p role="status">Restoring your session...</p></main>;
  return <>
    {error && <div className="app-error" role="alert">{error} <button onClick={() => setError("")}>Dismiss</button></div>}
    {!user ? (authView === "register" ? <Register onRegister={() => setAuthView("login")} onOpenLogin={() => setAuthView("login")} /> : <Login onLogin={handleLogin} onOpenRegister={() => setAuthView("register")} />) : (
      <div className={`app-shell ${selectedChat ? "has-selected-chat" : ""} ${activeView === "profile" ? "profile-active" : activeView === "settings" ? "settings-active" : ""}`}>
        <NavigationRail user={user} activeView={activeView} setActiveView={setActiveView} onLogout={handleLogout} onHomeClick={() => { setSelectedChat(null); setActiveView("home"); }} />
        {activeView === "profile" ? <Profile key={userId} onLogout={handleLogout} authToken="cookie" /> : activeView === "settings" ? <SettingsPage key={userId} authToken="cookie" onOpenProfile={() => setActiveView("profile")} onLogout={handleLogout} /> : <>
          <ChatSidebar chats={chatData} selectedChat={selectedChat} setSelectedChat={(id) => { setSelectedChat(id); setActiveView("chats"); document.title = "ChatApp"; }} onNewChat={handleNewChat} authToken="cookie" />
          <ChatWorkspace key={`${userId}:${selectedChat}`} chats={chatData} selectedChat={selectedChat} setChatData={setChatData} authToken="cookie" currentUserId={userId} onChatChanged={fetchChats} onBack={() => setSelectedChat(null)} />
        </>}
      </div>
    )}
  </>;
}
export default AppShell;
