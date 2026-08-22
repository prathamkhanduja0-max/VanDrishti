// ============================================================================
// Firebase Configuration — VanDrishti
// ============================================================================

import { initializeApp } from 'firebase/app';
import { getAuth, GoogleAuthProvider } from 'firebase/auth';

const firebaseConfig = {
  apiKey: "AIzaSyCbtM2lEa5gzToR7mEn5vlrUCxdXkcmz6Q",
  authDomain: "vandridhti.firebaseapp.com",
  projectId: "vandridhti",
  storageBucket: "vandridhti.firebasestorage.app",
  messagingSenderId: "350519618300",
  appId: "1:350519618300:web:b08e10e0e2ccd9561e8579",
  measurementId: "G-7YKXN2TWHT"
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
