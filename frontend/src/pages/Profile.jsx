import { useState, useEffect } from "react";
import { apiRequest } from "../services/api";
import { Pencil , LogOut } from "lucide-react";
import EditProfile from "./EditProfile";
import ConfirmationDialog from "../components/ConfirmationDialog";
import "./Profile.css";


function toProfile(user) {
  return { ...user, phone: user.phone_no ?? "", dob: user.dob ?? "", bio: user.bio ?? "" };
}

function formatDate(date){
  if (!date) return "";

  const parsedDate = new Date (`${date}T00:00:00`);

  if (Number.isNaN(parsedDate.getTime())){
    return date;
  }

  return parsedDate.toLocaleDateString("en-GB",{
    day: "2-digit",
    month:"short",
    year:"numeric",
  });
}

function Profile( {onLogout, authToken} ){
  const [profile, setProfile ] = useState(null);
  const [error, setError] = useState("");
  const[isEditing, setIsEditing] = useState(false);
  const[showLogoutDialog, setShowLogoutDialog] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiRequest("/users/me", { token: authToken })
      .then((user) => { if (!cancelled) setProfile(toProfile(user)); })
      .catch((error) => { if (!cancelled) setError(error.message); });
    return () => { cancelled = true; };
  }, [authToken]);

  const handleLogoutCancel = () =>{
    setShowLogoutDialog(false);
  };


  const handleSave = async (updatedProfile) =>{
    await apiRequest("/users/me", {
      method: "PUT",
      token: authToken,
      body: {
        name: updatedProfile.name.trim(),
        username: updatedProfile.username.trim(),
        phone_no: updatedProfile.phone.trim(),
        dob: updatedProfile.dob,
        bio: updatedProfile.bio,
      },
    });
    const user = await apiRequest("/users/me", { token: authToken });
    setProfile(toProfile(user));
    setIsEditing(false);
  };

  if (!profile) {
    return <main className="profile-page"><section className="profile-card">
      {error ? <p role="alert">{error}</p> : <p role="status">Loading profile...</p>}
    </section></main>;
  }

  if(isEditing) {
    return (
      <EditProfile
        profile={profile}
        onSave={handleSave}
        onCancel={() => setIsEditing(false)}
      />
    );
  }
 
  return (
    <main className="profile-page">
      <section className="profile-card">
        <div className="profile-header">
          <div className="profile-avatar" aria-label="Profile Avatar"/>
          <div className="profile-identity">
            <h2>{profile.name}</h2>
            <p>@{profile.username}</p>
          </div>
        </div>

        <div className="profile-details">
          <div className="profile-detail-row">
            <span>Email</span>
            <span>{profile.email}</span>
          </div>

          <div className="profile-detail-row">
            <span>Phone</span>
            <span>{profile.phone || "Not provided"}</span>
          </div>

          <div className="profile-detail-row">
            <span>Date of Birth</span>
            <span>{formatDate(profile.dob) || "Not provided"}</span>
          </div>

          <div className="profile-detail-row">
            <span>Bio</span>
            <span>{profile.bio || "Not provided"}</span>
          </div> 
        </div>

        <div className="profile-actions">
          <button 
            className="profile-button"
            onClick={()=> setIsEditing(true)}
          >
            <Pencil size={16}/>
            Edit profile
          </button>

          <button
            className="profile-button logout"
            onClick={() => setShowLogoutDialog(true)}
          >
            <LogOut size={16}/>
            Log out
          </button>
        </div>
      </section>
      {showLogoutDialog && (
        <ConfirmationDialog 
          title= "Log out of ChatApp?"
          description= "You'll need to log in again with your email and password to access your conversations."
          cancelLabel="Cancel"
          confirmLabel="Log out"
          danger={true}
          onCancel = {handleLogoutCancel}
          onConfirm={()=>{
            setShowLogoutDialog(false);
            onLogout();
          }}
        />
      )}

    </main>
    
  );
}

export default Profile;

