import { useState } from "react";
import "./EditProfile.css";

function EditProfile({ profile, onSave, onCancel }) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [formData , setFormData] = useState({
    name: profile.name,
    email: profile.email,
    current_password: "",
    new_password: "",
    profile_picture: profile.profile_picture || "",
    username: profile.username,
    bio: profile.bio,
    phone: profile.phone,
    dob: profile.dob,
  });

  const handleChange = (event) => {
    const {name ,value} = event.target;

    setFormData((previous) => ({
      ...previous,
      [name]: value,
    }));
  };

  const handleSubmit = async (event)=> {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      await onSave(formData);
    } catch (error) {
      setError(error.message || "Could not save profile.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className="edit-profile-page">
      <form className="edit-profile-card" onSubmit={handleSubmit}>
        <header className="edit-profile-header">
          <h1>Edit profile</h1>
          <p>Update how you appear to others.</p>
        </header>

        <div className="edit-avatar-section">
          <div className="edit-profile-avatar">{formData.profile_picture && <img src={formData.profile_picture} alt="Profile preview" />}</div>
          <label className="change-photo-button">Change photo
            <input type="file" accept="image/png,image/jpeg,image/webp" disabled={saving} onChange={(event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              if (file.size > 2 * 1024 * 1024) { setError("Photo must be at most 2 MB."); return; }
              const reader = new FileReader();
              reader.onload = () => setFormData((previous) => ({ ...previous, profile_picture: reader.result }));
              reader.onerror = () => setError("Could not read the selected photo.");
              reader.readAsDataURL(file);
            }} />
          </label>
          {formData.profile_picture && <button type="button" disabled={saving} onClick={() => setFormData((previous) => ({ ...previous, profile_picture: "" }))}>Remove photo</button>}
        </div>
        <div className="edit-form-field"><label htmlFor="edit-email">Email</label><input id="edit-email" name="email" type="email" value={formData.email} onChange={handleChange} required maxLength={255} /></div>
        <div className="edit-form-field"><label htmlFor="edit-current-password">Current password (required to change email or password)</label><input id="edit-current-password" name="current_password" type="password" autoComplete="current-password" value={formData.current_password} onChange={handleChange} maxLength={128} /></div>
        <div className="edit-form-field"><label htmlFor="edit-new-password">New password (optional, at least 8 characters)</label><input id="edit-new-password" name="new_password" type="password" autoComplete="new-password" value={formData.new_password} onChange={handleChange} minLength={8} maxLength={128} /></div>
        <div className="edit-form-field">
          <label htmlFor="edit-name">Name</label>
          <input 
            id ="edit-name"
            name="name"
            value={formData.name}
            onChange={handleChange}
            required
          />
        </div>

        <div className="edit-form-field">
          <label htmlFor="edit-username">Username</label>
          <input 
            id ="edit-username"
            name="username"
            value={formData.username}
            onChange={handleChange}
            required
          />
        </div>

        <div className="edit-form-field">
          <label htmlFor="edit-bio">Bio</label>
          <textarea
            id ="edit-bio"
            name="bio"
            value={formData.bio}
            onChange={handleChange}
            rows={3}
          />
        </div>

        <div className="edit-form-row">
          <div className="edit-form-field">
            <label htmlFor="edit-phone">Phone</label>
            <input 
              id ="edit-phone"
              name="phone"
              type="tel"
              value={formData.phone}
              onChange={handleChange}
            />
          </div>

          <div className="edit-form-field">
            <label htmlFor="edit-dob">Date of birth</label>
            <input 
              id ="edit-dob"
              name="dob"
              type="date"
              value={formData.dob}
              onChange={handleChange}
            />
          </div>
        </div>

        {error && <p role="alert">{error}</p>}
        <div className="edit-profile-actions">
          <button
            type="button"
            className="edit-cancel-button"
            disabled={saving}
            onClick={onCancel}
          >
            Cancel
          </button>

          <button 
            type="submit"
            className="edit-save-button"
            disabled={saving}
          >
            {saving ? "Saving..." : "Save Changes"}
          </button>
        </div>
      </form>
    </main>
  );
}

export default EditProfile;
