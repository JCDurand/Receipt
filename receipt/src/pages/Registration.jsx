import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../components/AuthContext";
import axiosClient from "../api/axiosClient";
import navbar_logo from "../assets/navbar_logo.png";
import "../styles/Registration.css";

const Registration = () => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  
  // UX States
  const [needsSignUp, setNeedsSignUp] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  
  const { attemptLogin } = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState("noError");
  const [errMsg, setErrMsg] = useState("");

  useEffect(() => {
    setError("noError");
    setErrMsg("");
    setPassword("");
    setConfirmPassword("");
  }, [needsSignUp]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    try {
      if (needsSignUp) {
        if (password !== confirmPassword) {
          setError("error");
          setErrMsg("Passwords do not match.");
          return;
        }

        await axiosClient.post('/register/', {
          email,
          username,
          password,
          first_name: firstName,
          last_name: lastName,
        });

        /* Log them in straight away, then send them to create their first bank account
           — they don't get into the rest of the site until they have at least one. */
        await attemptLogin(username, password);
        navigate("/accounts");
      } else {
        await attemptLogin(username, password);
        navigate("/dashboard");
      }
    } catch (error) {
      setError("error");
      /* /register/ says what was wrong (e.g. "Invalid email format.") in its `error` field */
      const serverMsg = error.response?.data?.error;
      setErrMsg(needsSignUp ? serverMsg || "Registration failed. Please try again." : "Invalid username or password.");
    }
  };

  const togglePasswordStyle = {
    position: "absolute",
    right: "12px",
    background: "none",
    border: "none",
    color: "#666",
    cursor: "pointer",
    padding: "0",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    height: "100%"
  };

  // SVG Icons for the view password button
  const EyeOpen = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
      <circle cx="12" cy="12" r="3"></circle>
    </svg>
  );

  const EyeClosed = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
      <line x1="1" y1="1" x2="23" y2="23"></line>
    </svg>
  );

  return (
    <div className="container" style={{display: "flex", paddingLeft: "50px", paddingRight: "50px"}}>
      <div className={`login-container${needsSignUp ? " is-signup" : ""}`}>
        <div className="login-header">
          <img src={navbar_logo} alt="Receipt site logo" />
          <h6>Your receipts, statements, and expenses <br/> all in one place</h6>
        </div>
  
        <form className="login-form" onSubmit={handleSubmit}>
          <h1>Welcome</h1>
          <hr />
          <div className="inputs">
            {needsSignUp ?
            <>
              <div className="input-row">
                <div className="input">
                  <label>First Name</label>
                  <input type="text" placeholder="First name" value={firstName} onChange={(e) => setFirstName(e.target.value)} required />
                </div>
                <div className="input">
                  <label>Last Name</label>
                  <input type="text" placeholder="Last name" value={lastName} onChange={(e) => setLastName(e.target.value)} required />
                </div>
              </div>
              <div className="input">
                <label>Email</label>
                <input type="email" placeholder="Email address" value={email} onChange={(e) => setEmail(e.target.value)} required />
              </div>
              <div className="input">
                <label>Username</label>
                <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} required />
              </div>
              <div className="input">
                <label>Password</label>
                <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    style={{ width: "100%", paddingRight: "40px" }}
                    required
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} style={togglePasswordStyle} tabIndex="-1" aria-label="Toggle password visibility">
                    {showPassword ? <EyeClosed /> : <EyeOpen />}
                  </button>
                </div>
              </div>
              <div className="input">
                <label>Confirm Password</label>
                <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                  <input
                    type={showConfirmPassword ? "text" : "password"}
                    placeholder="Re-enter password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    style={{ width: "100%", paddingRight: "40px" }}
                    required
                  />
                  <button type="button" onClick={() => setShowConfirmPassword(!showConfirmPassword)} style={togglePasswordStyle} tabIndex="-1" aria-label="Toggle confirm password visibility">
                    {showConfirmPassword ? <EyeClosed /> : <EyeOpen />}
                  </button>
                </div>
              </div>
            </>
            :
            <>
              <div className="input">
                <label>Username</label>
                <input type="text" placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} required />
              </div>
              <div className="input">
                <label>Password</label>
                <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                  <input
                    type={showPassword ? "text" : "password"}
                    placeholder="Password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    style={{ width: "100%", paddingRight: "40px" }}
                    required
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} style={togglePasswordStyle} tabIndex="-1" aria-label="Toggle password visibility">
                    {showPassword ? <EyeClosed /> : <EyeOpen />}
                  </button>
                </div>
              </div>
            </>}
          </div>

          {needsSignUp ?
          <>
            <button className="submit-btn" type="submit">Sign Up</button> 
            <div className="no-account-signup">
              <h4>Have an account?</h4>
              <h4 
                className="sign-up-suggestion"
                onClick={(e) => {
                  setNeedsSignUp(false)
                  setError("noError")
                  setErrMsg("")
                }}
                >Log In</h4>
            </div>
          </>
          : 
          <>
            <button className="submit-btn" type="submit">Log In</button>
            <div className="no-account-signup">
              <h4>Don't have an account?</h4>
              <h4 
                className="sign-up-suggestion"
                onClick={(e) => {
                  setNeedsSignUp(true)
                  setError("noError")
                  setErrMsg("")
                }}
                >Sign Up</h4>
            </div>
          </>
          }
        </form>
      </div>
      
      {error === "error" && (
        <div className="failed-login">
          <p>{errMsg}</p>
        </div>
      )}
    </div>
  );
};

export default Registration;