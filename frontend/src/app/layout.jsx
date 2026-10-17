import { Bricolage_Grotesque, Figtree } from "next/font/google";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

const display = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage", display: "swap" });
const body = Figtree({ subsets: ["latin"], variable: "--font-figtree", display: "swap" });

export const metadata = {
  title: "StudentLife AI",
  description: "Études, carrière et quotidien au même endroit.",
};

export const viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }) {
  return (
    <html lang="fr" className={`${display.variable} ${body.variable}`}>
      <body className="font-sans antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
