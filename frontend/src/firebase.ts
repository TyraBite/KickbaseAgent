import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";
import { getFirestore } from "firebase/firestore";

// Selbes Firebase-Projekt/Config wie die bestehende index.html (Repo-Root) -
// Firebase-Web-apiKeys sind nicht geheim (Zugriff wird ueber firestore.rules
// + Firebase Auth geregelt, nicht ueber Geheimhaltung des Keys).
const firebaseConfig = {
  apiKey: "AIzaSyDaKr1cKLxqqA8EGauwSaNNOpsPQedHRQs",
  authDomain: "kickbaseagent.firebaseapp.com",
  projectId: "kickbaseagent",
  storageBucket: "kickbaseagent.firebasestorage.app",
  messagingSenderId: "622019870310",
  appId: "1:622019870310:web:45410188371a0327a1b7a7",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db = getFirestore(app);
