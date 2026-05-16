import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "TSS Vault | MPC Multi-Party Wallet",
  description: "Secure, threshold signature scheme powered cryptocurrency wallet.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className={`${inter.className} antialiased bg-[#0f111a] text-slate-200 min-h-screen`}>
        {children}
      </body>
    </html>
  );
}
