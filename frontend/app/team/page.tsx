"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, Users, Plus, UserCheck, Loader2 } from "lucide-react";
import { api } from "@/lib/api";

interface Executive {
  id: string;
  email: string;
  full_name: string;
  role: string;
  node_id: number;
  is_active: boolean;
  last_login: string | null;
}

export default function TeamPage() {
  const [executives, setExecutives] = useState<Executive[]>([]);
  const [loading, setLoading] = useState(true);
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("EXECUTIVE");
  const [inviteNodeId, setInviteNodeId] = useState(2);
  const [inviteLoading, setInviteLoading] = useState(false);
  const [inviteSuccess, setInviteSuccess] = useState(false);
  const router = useRouter();

  useEffect(() => {
    fetchTeam();
  }, []);

  const fetchTeam = async () => {
    try {
      const { data } = await api.get("/companies/me/executives");
      setExecutives(data.executives);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setInviteLoading(true);
    try {
      await api.post("/auth/invite", {
        email: inviteEmail,
        role: inviteRole,
        node_id: inviteNodeId
      });
      setInviteSuccess(true);
      setTimeout(() => {
        setShowInvite(false);
        setInviteSuccess(false);
        setInviteEmail("");
      }, 2000);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to send invitation");
    } finally {
      setInviteLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center">
            <button 
              onClick={() => router.push("/dashboard")}
              className="flex items-center text-slate-400 hover:text-white transition-colors mr-4"
            >
              <ArrowLeft className="w-5 h-5 mr-2" />
              Back
            </button>
            <h1 className="text-2xl font-bold text-white">Team</h1>
          </div>
          <button
            onClick={() => setShowInvite(true)}
            className="bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl font-medium transition-all flex items-center space-x-2"
          >
            <Plus className="w-5 h-5" />
            <span>Invite Executive</span>
          </button>
        </div>

        {/* Invite Modal */}
        {showInvite && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          >
            <motion.div 
              initial={{ scale: 0.9 }}
              animate={{ scale: 1 }}
              className="glass p-6 rounded-2xl w-full max-w-md"
            >
              <h2 className="text-xl font-bold text-white mb-4">Invite Executive</h2>
              
              {inviteSuccess ? (
                <div className="text-center py-4">
                  <div className="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center mx-auto mb-3">
                    <UserCheck className="w-6 h-6 text-green-400" />
                  </div>
                  <p className="text-green-400">Invitation sent!</p>
                </div>
              ) : (
                <form onSubmit={handleInvite} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-slate-300 mb-1">Email</label>
                    <input
                      type="email"
                      required
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-4 py-2 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      placeholder="new.executive@company.com"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">Role</label>
                      <select
                        value={inviteRole}
                        onChange={(e) => setInviteRole(e.target.value)}
                        className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-4 py-2 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value="CEO">CEO</option>
                        <option value="CFO">CFO</option>
                        <option value="BOARD">Board Member</option>
                        <option value="EXECUTIVE">Executive</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">Node</label>
                      <select
                        value={inviteNodeId}
                        onChange={(e) => setInviteNodeId(parseInt(e.target.value))}
                        className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-4 py-2 text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                      >
                        {[2, 3, 4, 5].map(n => (
                          <option key={n} value={n}>Node {n}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="flex space-x-3 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowInvite(false)}
                      className="flex-1 bg-slate-700 hover:bg-slate-600 text-white rounded-xl px-4 py-2 transition-all"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={inviteLoading}
                      className="flex-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl px-4 py-2 transition-all flex items-center justify-center"
                    >
                      {inviteLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Send Invite"}
                    </button>
                  </div>
                </form>
              )}
            </motion.div>
          </motion.div>
        )}

        {/* Team List */}
        <div className="glass rounded-2xl overflow-hidden">
          <div className="p-6 border-b border-slate-700/50">
            <h2 className="text-lg font-semibold text-white flex items-center">
              <Users className="w-5 h-5 mr-2 text-indigo-400" />
              Executives ({executives.length})
            </h2>
          </div>
          <div className="divide-y divide-slate-700/50">
            {executives.map((exec) => (
              <div key={exec.id} className="p-6 flex items-center justify-between">
                <div className="flex items-center space-x-4">
                  <div className="w-10 h-10 rounded-full bg-indigo-500/20 flex items-center justify-center">
                    <span className="text-indigo-400 font-medium">
                      {exec.full_name.split(' ').map(n => n[0]).join('')}
                    </span>
                  </div>
                  <div>
                    <p className="font-medium text-white">{exec.full_name}</p>
                    <p className="text-sm text-slate-400">{exec.email}</p>
                    <div className="flex items-center space-x-2 mt-1">
                      <span className="text-xs bg-slate-700/50 text-slate-300 px-2 py-0.5 rounded">
                        {exec.role}
                      </span>
                      <span className="text-xs bg-indigo-500/20 text-indigo-300 px-2 py-0.5 rounded">
                        Node {exec.node_id}
                      </span>
                    </div>
                  </div>
                </div>
                <div className="text-right">
                  <span className={`inline-block w-2 h-2 rounded-full ${exec.is_active ? 'bg-green-400' : 'bg-slate-500'}`} />
                  <p className="text-xs text-slate-500 mt-1">
                    {exec.last_login ? 'Active recently' : 'Never logged in'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
