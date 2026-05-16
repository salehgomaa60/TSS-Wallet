"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, ShieldCheck, LayoutDashboard, History, Settings } from "lucide-react";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    // Guard: redirect to home if this tab has no token in localStorage.
    // Because localStorage is per-tab, a fresh tab or private window
    // will always land here with no token and be redirected to login —
    // exactly what we want for independent vault testing.
    if (!localStorage.getItem("token")) {
      router.push("/");
    }
  }, [router]);

  if (!mounted) return null;

  const handleSignOut = () => {
    // Clear only this tab's session — other open tabs are unaffected.
    localStorage.removeItem("token");
    localStorage.removeItem("vault_info");
    localStorage.removeItem("user_info");
    router.push("/");
  };

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <div className="w-64 glass border-r border-t-0 border-b-0 border-l-0 flex flex-col z-10">
        <div className="p-6 flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <span className="font-bold text-xl tracking-tight text-white">TSS Vault</span>
        </div>

        <nav className="flex-1 px-4 py-4 space-y-1">
          <a href="/dashboard" className="flex items-center space-x-3 px-3 py-2.5 bg-indigo-500/10 text-indigo-400 rounded-xl transition-all font-medium">
            <LayoutDashboard className="w-5 h-5" />
            <span>Dashboard</span>
          </a>
          <a href="#" className="flex items-center space-x-3 px-3 py-2.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 rounded-xl transition-all font-medium">
            <History className="w-5 h-5" />
            <span>History</span>
          </a>
          <a href="#" className="flex items-center space-x-3 px-3 py-2.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800/50 rounded-xl transition-all font-medium">
            <Settings className="w-5 h-5" />
            <span>Settings</span>
          </a>
        </nav>

        <div className="p-4 border-t border-slate-800">
          <button
            onClick={handleSignOut}
            className="flex items-center space-x-3 px-3 py-2.5 w-full text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-xl transition-all font-medium"
          >
            <LogOut className="w-5 h-5" />
            <span>Sign Out</span>
          </button>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-auto relative">
        {children}
      </div>
    </div>
  );
}
