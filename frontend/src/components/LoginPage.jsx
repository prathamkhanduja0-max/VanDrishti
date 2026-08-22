import React, { useState } from 'react';
import { Trees, Phone, ArrowLeft } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import './LoginPage.css';

// Google "G" logo SVG
const GoogleLogo = () => (
  <svg width="18" height="18" viewBox="0 0 48 48" style={{ marginRight: '8px' }}>
    <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
    <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
    <path fill="#FBBC05" d="M10.53 28.59a14.5 14.5 0 0 1 0-9.18l-7.98-6.19a24.01 24.01 0 0 0 0 21.56l7.98-6.19z"/>
    <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
  </svg>
);

// Phone step constants
const PHONE_STEP = {
  NONE: 'none',
  ENTER_PHONE: 'enter_phone',
  ENTER_OTP: 'enter_otp',
};

export default function LoginPage() {
  const { signInWithGoogle, signInWithEmail, signUpWithEmail, sendOtp, verifyOtp } = useAuth();

  // Email/password state
  const [isSignUp, setIsSignUp] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  // Phone auth state
  const [phoneStep, setPhoneStep] = useState(PHONE_STEP.NONE);
  const [countryCode, setCountryCode] = useState('+91');
  const [phone, setPhone] = useState('');
  const [otp, setOtp] = useState('');

  // Shared state
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  // ── Google ──────────────────────────────────────────────────────────────────
  const handleGoogleSignIn = async () => {
    setError(null);
    setLoading(true);
    try {
      await signInWithGoogle();
    } catch (err) {
      if (err.code === 'auth/popup-closed-by-user' || err.code === 'auth/cancelled-popup-request') {
        setError(null);
      } else {
        setError(err.message || 'Google sign-in failed. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  // ── Email / Password ────────────────────────────────────────────────────────
  const handleEmailAuth = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isSignUp) {
        if (!name.trim()) throw new Error('Please enter your name.');
        await signUpWithEmail(email, password, name);
      } else {
        await signInWithEmail(email, password);
      }
    } catch (err) {
      let msg = err.message;
      if (err.code === 'auth/user-not-found' || err.code === 'auth/wrong-password') {
        msg = 'Invalid email or password.';
      } else if (err.code === 'auth/email-already-in-use') {
        msg = 'This email is already in use.';
      } else if (err.code === 'auth/invalid-email') {
        msg = 'Please enter a valid email address.';
      } else if (err.code === 'auth/weak-password') {
        msg = 'Password should be at least 6 characters.';
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // ── Phone — Send OTP ────────────────────────────────────────────────────────
  const handleSendOtp = async (e) => {
    e.preventDefault();
    setError(null);
    if (!phone.trim()) {
      setError('Please enter your phone number.');
      return;
    }
    setLoading(true);
    try {
      const fullNumber = `${countryCode}${phone.replace(/\D/g, '')}`;
      await sendOtp(fullNumber);
      setPhoneStep(PHONE_STEP.ENTER_OTP);
    } catch (err) {
      let msg = err.message || 'Failed to send OTP. Please try again.';
      if (err.code === 'auth/invalid-phone-number') {
        msg = 'Invalid phone number. Please include the full number (e.g. 9876543210).';
      } else if (err.code === 'auth/too-many-requests') {
        msg = 'Too many attempts. Please wait a few minutes and try again.';
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // ── Phone — Verify OTP ──────────────────────────────────────────────────────
  const handleVerifyOtp = async (e) => {
    e.preventDefault();
    setError(null);
    if (!otp.trim()) {
      setError('Please enter the OTP code.');
      return;
    }
    setLoading(true);
    try {
      await verifyOtp(otp);
      // Auth state change will redirect automatically
    } catch (err) {
      let msg = err.message || 'Verification failed. Please try again.';
      if (err.code === 'auth/invalid-verification-code') {
        msg = 'Incorrect OTP code. Please check and try again.';
      } else if (err.code === 'auth/code-expired') {
        msg = 'OTP has expired. Please go back and request a new code.';
      }
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  // ── Reset phone flow ────────────────────────────────────────────────────────
  const resetPhoneFlow = () => {
    setPhoneStep(PHONE_STEP.NONE);
    setPhone('');
    setOtp('');
    setError(null);
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="login-page">
      {/* Hidden reCAPTCHA container — required by Firebase Phone Auth */}
      <div id="recaptcha-container" />

      <div className="login-card">
        {/* Brand */}
        <div className="login-brand">
          <div className="login-brand-icon">
            <Trees size={28} />
          </div>
          <div className="login-brand-title">
            Van<span>Drishti</span>
          </div>
        </div>

        <div className="login-subtitle">
          AI-Powered Forest Intelligence Platform<br />
          Tree Crown Detection • Fire Monitoring • Patrol Routing
        </div>

        {/* ── Phone Flow ───────────────────────────────────────────────────── */}
        {phoneStep !== PHONE_STEP.NONE ? (
          <div className="phone-auth-section">
            {phoneStep === PHONE_STEP.ENTER_PHONE && (
              <form onSubmit={handleSendOtp} className="login-form">
                <p className="phone-step-label">Enter your phone number</p>
                <div className="phone-input-row">
                  <input
                    type="text"
                    value={countryCode}
                    onChange={(e) => setCountryCode(e.target.value)}
                    className="form-input country-code-input"
                    maxLength={5}
                    aria-label="Country code"
                  />
                  <input
                    type="tel"
                    placeholder="9876543210"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="form-input phone-number-input"
                    autoComplete="tel"
                    autoFocus
                  />
                </div>
                <button type="submit" disabled={loading} className="login-submit-btn">
                  {loading ? 'Sending OTP...' : 'Send OTP'}
                </button>
                <button
                  type="button"
                  onClick={resetPhoneFlow}
                  className="phone-back-btn"
                >
                  <ArrowLeft size={14} style={{ marginRight: '4px' }} />
                  Back to Sign In
                </button>
              </form>
            )}

            {phoneStep === PHONE_STEP.ENTER_OTP && (
              <form onSubmit={handleVerifyOtp} className="login-form">
                <p className="phone-step-label">
                  Enter the 6-digit OTP sent to<br />
                  <strong>{countryCode} {phone}</strong>
                </p>
                <div className="form-group">
                  <input
                    type="text"
                    inputMode="numeric"
                    placeholder="_ _ _ _ _ _"
                    value={otp}
                    onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
                    className="form-input otp-input"
                    maxLength={6}
                    autoFocus
                    autoComplete="one-time-code"
                  />
                </div>
                <button type="submit" disabled={loading} className="login-submit-btn">
                  {loading ? 'Verifying...' : 'Verify & Sign In'}
                </button>
                <button
                  type="button"
                  onClick={() => { setPhoneStep(PHONE_STEP.ENTER_PHONE); setOtp(''); setError(null); }}
                  className="phone-back-btn"
                >
                  <ArrowLeft size={14} style={{ marginRight: '4px' }} />
                  Change number / Resend OTP
                </button>
              </form>
            )}
          </div>
        ) : (
          <>
            {/* ── Email & Password Form ───────────────────────────────────── */}
            <form onSubmit={handleEmailAuth} className="login-form">
              {isSignUp && (
                <div className="form-group">
                  <input
                    type="text"
                    placeholder="Full Name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    className="form-input"
                    autoComplete="off"
                  />
                </div>
              )}
              <div className="form-group">
                <input
                  type="email"
                  placeholder="Email Address"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="form-input"
                  autoComplete="off"
                />
              </div>
              <div className="form-group">
                <input
                  type="password"
                  placeholder="Password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="form-input"
                  autoComplete="new-password"
                />
              </div>

              <button type="submit" disabled={loading} className="login-submit-btn">
                {loading ? 'Processing...' : isSignUp ? 'Create Account' : 'Sign In'}
              </button>
            </form>

            {/* Toggle Mode */}
            <div className="toggle-mode">
              {isSignUp ? (
                <span>
                  Already have an account?{' '}
                  <button type="button" onClick={() => { setIsSignUp(false); setError(null); }} className="toggle-btn">
                    Sign In
                  </button>
                </span>
              ) : (
                <span>
                  Don't have an account?{' '}
                  <button type="button" onClick={() => { setIsSignUp(true); setError(null); }} className="toggle-btn">
                    Sign Up
                  </button>
                </span>
              )}
            </div>

            {/* Divider */}
            <div className="login-divider">
              <div className="login-divider-line" />
              <span className="login-divider-text">or</span>
              <div className="login-divider-line" />
            </div>

            {/* Google Sign-In Button */}
            <button
              className="login-google-btn"
              onClick={handleGoogleSignIn}
              disabled={loading}
            >
              <GoogleLogo />
              {loading ? 'Please wait...' : 'Continue with Google'}
            </button>

            {/* Phone Sign-In Button */}
            <button
              className="login-phone-btn"
              onClick={() => { setPhoneStep(PHONE_STEP.ENTER_PHONE); setError(null); }}
              disabled={loading}
            >
              <Phone size={18} style={{ marginRight: '8px' }} />
              Continue with Phone
            </button>
          </>
        )}

        {/* Error Message */}
        {error && (
          <div className="login-error">
            {error}
          </div>
        )}

        {/* Footer */}
        <div className="login-footer">
          By signing in, you agree to access VanDrishti's geospatial
          intelligence tools for authorized forest monitoring operations.
        </div>
      </div>
    </div>
  );
}
