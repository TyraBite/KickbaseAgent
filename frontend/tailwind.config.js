/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "media",
  theme: {
    extend: {
      // An Kickbases eigenes Markenbild angelehnt (kräftiges Grün auf
      // dunklem Grund) - kein offizieller Marken-Hex-Wert verifiziert
      // (Kickbase-Brand-Seiten blockieren automatisierte Abrufe), bewusst
      // als Annäherung gewählt statt geraten-exakt behauptet.
      colors: {
        brand: {
          50: "#eafff4",
          100: "#c8ffe3",
          200: "#93ffc7",
          300: "#54f5a4",
          400: "#22dd80",
          500: "#0fc46a",
          600: "#0a9d55",
          700: "#0a7a45",
          800: "#0c5f38",
          900: "#0b4e30",
          950: "#032c1a",
        },
      },
    },
  },
  plugins: [],
};
