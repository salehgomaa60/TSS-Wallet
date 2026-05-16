"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Shield, UserPlus, Loader2, ArrowLeft, CheckCircle2, Server, KeyRound, FileCheck } from "lucide-react";
import { api } from "@/lib/api";
// No cookie import — we use localStorage for per-tab session isolation

export default function SignupPage() {
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({
    email: "",
    password: "",
    full_name: "",
    company_name: "",
    threshold: 2,
    total_signers: 3,
    spending_limit_eth: 10
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState(0);
  const router = useRouter();

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    setStep(2);

    // Simulate progress steps
    const steps = [
      { msg: "Creating company...", prog: 20 },
      { msg: "Running DKG across TSS nodes...", prog: 50 },
      { msg: "Deploying vault contract...", prog: 80 },
      { msg: "Finalizing setup...", prog: 100 }
    ];

    for (const s of steps) {
      await new Promise(r => setTimeout(r, 1500));
      setProgress(s.prog);
    }

    try {
      const { data } = await api.post("/auth/register", {
        ...formData,
        threshold: parseInt(formData.threshold.toString()),
        total_signers: parseInt(formData.total_signers.toString()),
        spending_limit_eth: parseFloat(formData.spending_limit_eth.toString())
      });
      
      // Per-tab session storage — keeps each tab independent
      localStorage.setItem("token", data.access_token);
      if (data.company) {
        localStorage.setItem("vault_info", JSON.stringify({
          eth_address:      data.company.eth_address,
          contract_address: data.company.contract_address,
          company_name:     data.company.name,
        }));
      }
      if (data.user) {
        localStorage.setItem("user_info", JSON.stringify({
          email:     data.user.email,
          full_name: data.user.full_name,
          role:      data.user.role,
        }));
      }
      setStep(3);

      setTimeout(() => {
        router.push("/dashboard");
      }, 2000);
    } catch (err: any) {
      let errorMessage = "Registration failed";
      if (err.response?.data?.detail) {
        if (typeof err.response.data.detail === 'string') {
          errorMessage = err.response.data.detail;
        } else if (typeof err.response.data.detail === 'object') {
          errorMessage = JSON.stringify(err.response.data.detail);
        }
      } else if (err.message) {
        errorMessage = err.message;
      }
      setError(errorMessage);
      setStep(1);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-lg"
      >
        {/* Back button */}
        <button 
          onClick={() => router.push("/")}
          className="flex items-center text-slate-400 hover:text-white mb-8 transition-colors"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to home
        </button>

        <div className="glass p-8 rounded-2xl shadow-2xl relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500" />
          
          <div className="flex flex-col items-center mb-8">
            <div className="w-16 h-16 rounded-full bg-indigo-500/10 flex items-center justify-center mb-4 border border-indigo-500/20">
              <Shield className="w-8 h-8 text-indigo-400" />
            </div>
            <h1 className="text-2xl font-bold text-white">Create Your Vault</h1>
            <p className="text-slate-400 mt-2 text-sm text-center">
              Set up your corporate treasury in minutes
            </p>
          </div>

          <AnimatePresence mode="wait">
            {step === 1 && (
              <motion.form 
                key="form"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onSubmit={handleSubmit} 
                className="space-y-4"
              >
                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2">
                    <label className="block text-sm font-medium text-slate-300 mb-1">Company Name</label>
                    <input 
                      type="text" 
                      name="company_name"
                      required
                      value={formData.company_name}
                      onChange={handleInputChange}
                      className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-4 py-3 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all placeholder:text-slate-600"
                      placeholder="Acme Corp"
                    />
                  </div>
                  <div className="col-span-2">
                    <label className="block text-sm font-medium text-slate-300 mb-1">Your Email</label>
                    <input 
                      type="email" 
                      name="email"
                      required
                      value={formData.email}
                      onChange={handleInputChange}
                      className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-4 py-3 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all placeholder:text-slate-600"
                      placeholder="you@company.com"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">Full Name</label>
                    <input 
                      type="text" 
                      name="full_name"
                      required
                      value={formData.full_name}
                      onChange={handleInputChange}
                      className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-4 py-3 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all placeholder:text-slate-600"
                      placeholder="John Doe"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">Password</label>
                    <input 
                      type="password" 
                      name="password"
                      required
                      value={formData.password}
                      onChange={handleInputChange}
                      className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-4 py-3 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all placeholder:text-slate-600"
                      placeholder="••••••••"
                    />
                  </div>
                </div>

                <div className="border-t border-slate-700/50 pt-4 mt-4">
                  <h3 className="text-sm font-medium text-slate-300 mb-3">Vault Configuration</h3>
                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Threshold (M)</label>
                      <select 
                        name="threshold"
                        value={formData.threshold}
                        onChange={handleInputChange}
                        className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value={1}>1</option>
                        <option value={2}>2</option>
                        <option value={3}>3</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Total Signers (N)</label>
                      <select 
                        name="total_signers"
                        value={formData.total_signers}
                        onChange={handleInputChange}
                        className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value={2}>2</option>
                        <option value={3}>3</option>
                        <option value={4}>4</option>
                        <option value={5}>5</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">Daily Limit (ETH)</label>
                      <input 
                        type="number" 
                        name="spending_limit_eth"
                        value={formData.spending_limit_eth}
                        onChange={handleInputChange}
                        className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      />
                    </div>
                  </div>
                </div>

                {error && (
                  <motion.div 
                    initial={{ opacity: 0 }} 
                    animate={{ opacity: 1 }} 
                    className="p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm"
                  >
                    {error}
                  </motion.div>
                )}

                <button 
                  disabled={loading}
                  type="submit" 
                  className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white rounded-xl px-4 py-3 font-medium transition-all shadow-lg shadow-indigo-500/25 flex items-center justify-center space-x-2"
                >
                  {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : (
                    <><UserPlus className="w-5 h-5" /> <span>Create Vault</span></>
                  )}
                </button>

                <p className="text-xs text-slate-500 text-center">
                  By creating a vault, you agree to our Terms of Service and Privacy Policy
                </p>
              </motion.form>
            )}

            {step === 2 && (
              <motion.div 
                key="progress"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="py-8"
              >
                <div className="flex flex-col items-center">
                  <div className="w-full max-w-xs mb-6">
                    <div className="h-2 bg-slate-700/50 rounded-full overflow-hidden">
                      <motion.div 
                        className="h-full bg-gradient-to-r from-indigo-500 to-purple-500"
                        initial={{ width: 0 }}
                        animate={{ width: `${progress}%` }}
                        transition={{ duration: 0.5 }}
                      />
                    </div>
                    <p className="text-center text-sm text-slate-400 mt-2">{progress}%</p>
                  </div>
                  
                  <div className="space-y-3 w-full max-w-xs">
                    <div className={`flex items-center space-x-3 ${progress >= 20 ? 'text-indigo-400' : 'text-slate-600'}`}>
                      <Server className="w-5 h-5" />
                      <span className="text-sm">Creating company...</span>
                      {progress >= 20 && <CheckCircle2 className="w-4 h-4 ml-auto" />}
                    </div>
                    <div className={`flex items-center space-x-3 ${progress >= 50 ? 'text-indigo-400' : 'text-slate-600'}`}>
                      <KeyRound className="w-5 h-5" />
                      <span className="text-sm">Running DKG...</span>
                      {progress >= 50 && <CheckCircle2 className="w-4 h-4 ml-auto" />}
                    </div>
                    <div className={`flex items-center space-x-3 ${progress >= 80 ? 'text-indigo-400' : 'text-slate-600'}`}>
                      <FileCheck className="w-5 h-5" />
                      <span className="text-sm">Deploying contract...</span>
                      {progress >= 80 && <CheckCircle2 className="w-4 h-4 ml-auto" />}
                    </div>
                  </div>
                </div>
              </motion.div>
            )}

            {step === 3 && (
              <motion.div 
                key="success"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="py-8 text-center"
              >
                <div className="w-16 h-16 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-4">
                  <CheckCircle2 className="w-8 h-8 text-green-400" />
                </div>
                <h3 className="text-xl font-semibold text-white mb-2">Vault Created!</h3>
                <p className="text-slate-400 text-sm">Redirecting to dashboard...</p>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="mt-6 text-center">
            <p className="text-sm text-slate-400">
              Already have an account?{" "}
              <button 
                type="button"
                onClick={() => router.push("/login")}
                className="text-indigo-400 hover:text-indigo-300 transition-colors"
              >
                Sign in
              </button>
            </p>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
