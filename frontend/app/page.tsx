"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Shield, Fingerprint, LogIn, UserPlus, Loader2, ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import Cookies from "js-cookie";

export default function LandingPage() {
  const router = useRouter();

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Hero Section */}
      <div className="relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-900/20 via-purple-900/10 to-slate-950" />
        
        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-20 pb-32">
          {/* Navigation */}
          <nav className="flex justify-between items-center mb-20">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-500/20 flex items-center justify-center border border-indigo-500/30">
                <Shield className="w-6 h-6 text-indigo-400" />
              </div>
              <span className="text-xl font-bold text-white">TSS Vault</span>
            </div>
            <div className="flex items-center space-x-4">
              <button 
                onClick={() => router.push("/login")}
                className="text-slate-300 hover:text-white transition-colors"
              >
                Sign In
              </button>
              <button 
                onClick={() => router.push("/signup")}
                className="bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2.5 rounded-xl font-medium transition-all"
              >
                Get Started
              </button>
            </div>
          </nav>

          {/* Hero Content */}
          <div className="text-center max-w-4xl mx-auto">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6 }}
            >
              <h1 className="text-5xl md:text-7xl font-bold mb-6 leading-tight">
                Enterprise Crypto Treasury.
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
                  {" "}No MetaMask Required.
                </span>
              </h1>
              <p className="text-xl text-slate-400 mb-10 max-w-2xl mx-auto">
                Secure multi-signature treasury management powered by Threshold Signature Scheme. 
                Your private key never exists in one place.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
                <button 
                  onClick={() => router.push("/signup")}
                  className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white px-8 py-4 rounded-xl font-semibold text-lg transition-all shadow-lg shadow-indigo-500/25 flex items-center space-x-2"
                >
                  <span>Create Your Vault</span>
                  <ArrowRight className="w-5 h-5" />
                </button>
                <button 
                  onClick={() => router.push("/login")}
                  className="bg-slate-800/50 hover:bg-slate-800 text-white px-8 py-4 rounded-xl font-semibold text-lg transition-all border border-slate-700"
                >
                  Sign In
                </button>
              </div>
            </motion.div>
          </div>
        </div>
      </div>

      {/* How It Works */}
      <div className="py-24 bg-slate-900/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="text-3xl font-bold text-center mb-16">How It Works</h2>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              {
                icon: <Fingerprint className="w-8 h-8" />,
                title: "1. Email Login",
                description: "No MetaMask needed. Just email and password with enterprise-grade security."
              },
              {
                icon: <Shield className="w-8 h-8" />,
                title: "2. M-of-N Approvals",
                description: "Configure your treasury policy. Require 2-of-3 or 3-of-5 executive approvals."
              },
              {
                icon: <LogIn className="w-8 h-8" />,
                title: "3. Gas Abstraction",
                description: "We pay all gas fees. Your team never needs to hold ETH or manage wallets."
              }
            ].map((step, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                viewport={{ once: true }}
                className="glass p-8 rounded-2xl"
              >
                <div className="w-14 h-14 rounded-xl bg-indigo-500/20 flex items-center justify-center mb-6 text-indigo-400">
                  {step.icon}
                </div>
                <h3 className="text-xl font-semibold mb-3">{step.title}</h3>
                <p className="text-slate-400">{step.description}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </div>

      {/* CTA Section */}
      <div className="py-24">
        <div className="max-w-4xl mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold mb-6">Ready to secure your treasury?</h2>
          <p className="text-slate-400 mb-8">Join companies using TSS Vault for secure, compliant crypto asset management.</p>
          <button 
            onClick={() => router.push("/signup")}
            className="bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white px-8 py-4 rounded-xl font-semibold text-lg transition-all shadow-lg shadow-indigo-500/25"
          >
            Get Started for Free
          </button>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-slate-800 py-12">
        <div className="max-w-7xl mx-auto px-4 text-center text-slate-500">
          <p>© 2025 TSS Vault. Built for enterprise security.</p>
        </div>
      </footer>
    </div>
  );
}
