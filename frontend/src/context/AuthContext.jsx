import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import { 
  onAuthStateChanged, 
  signInWithPopup, 
  signOut,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  updateProfile,
  signInWithPhoneNumber,
  RecaptchaVerifier
} from 'firebase/auth';
import { auth, googleProvider } from '../firebase/firebaseConfig';

const AuthContext = createContext(null);

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const confirmationResultRef = useRef(null);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (firebaseUser) => {
      setUser(firebaseUser);
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  const signInWithGoogle = async () => {
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (error) {
      console.error('Google sign-in failed:', error);
      throw error;
    }
  };

  const signUpWithEmail = async (email, password, displayName) => {
    try {
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);
      if (displayName) {
        await updateProfile(userCredential.user, { displayName });
      }
      // Re-trigger user state updates
      setUser({ ...auth.currentUser });
    } catch (error) {
      console.error('Email sign-up failed:', error);
      throw error;
    }
  };

  const signInWithEmail = async (email, password) => {
    try {
      await signInWithEmailAndPassword(auth, email, password);
    } catch (error) {
      console.error('Email sign-in failed:', error);
      throw error;
    }
  };

  const logout = async () => {
    try {
      await signOut(auth);
    } catch (error) {
      console.error('Logout failed:', error);
      throw error;
    }
  };

  const sendOtp = async (phoneNumber) => {
    try {
      // Create reCAPTCHA verifier only once — reuse if it already exists
      if (!window.recaptchaVerifier) {
        window.recaptchaVerifier = new RecaptchaVerifier(auth, 'recaptcha-container', {
          size: 'invisible',
          callback: () => {},
        });
        await window.recaptchaVerifier.render();
      }
      const result = await signInWithPhoneNumber(auth, phoneNumber, window.recaptchaVerifier);
      confirmationResultRef.current = result;
    } catch (error) {
      console.error('Send OTP failed:', error);
      // On failure, reset the widget (not destroy) so user can retry
      if (window.recaptchaVerifier) {
        try {
          const widgetId = await window.recaptchaVerifier.render();
          window.grecaptcha?.reset(widgetId);
        } catch {
          // If reset also fails, fully destroy so a fresh one is made next attempt
          window.recaptchaVerifier.clear();
          window.recaptchaVerifier = null;
        }
      }
      throw error;
    }
  };

  const verifyOtp = async (otp) => {
    try {
      if (!confirmationResultRef.current) {
        throw new Error('No OTP was sent. Please request a new code.');
      }
      await confirmationResultRef.current.confirm(otp);
      confirmationResultRef.current = null;
    } catch (error) {
      console.error('Verify OTP failed:', error);
      throw error;
    }
  };

  const value = {
    user,
    loading,
    signInWithGoogle,
    signUpWithEmail,
    signInWithEmail,
    sendOtp,
    verifyOtp,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}
