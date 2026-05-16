"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, ClipboardList, Loader2, Download } from "lucide-react";
import { api } from "@/lib/api";

interface AuditEntry {
  id: string;
  action: string;
  details: any;
  timestamp: string;
  user_id: string | null;
}

export default function AuditPage() {
  const [logs, setLogs] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    fetchLogs();
  }, []);

  const fetchLogs = async () => {
    try {
      // This would be the admin endpoint - for now we mock
      // const { data } = await api.get("/admin/audit");
      setLogs([
        {
          id: "1",
          action: "COMPANY_CREATED",
          details: { company_name: "Test Corp" },
          timestamp: new Date().toISOString(),
          user_id: null
        },
        {
          id: "2",
          action: "TX_PROPOSED",
          details: { value_eth: 0.5 },
          timestamp: new Date().toISOString(),
          user_id: null
        }
      ]);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const formatAction = (action: string) => {
    return action.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  };

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleString();
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
            <h1 className="text-2xl font-bold text-white">Audit Log</h1>
          </div>
          <button className="bg-slate-800 hover:bg-slate-700 text-white px-4 py-2 rounded-xl font-medium transition-all flex items-center space-x-2">
            <Download className="w-4 h-4" />
            <span>Export CSV</span>
          </button>
        </div>

        {/* Audit Log */}
        <div className="glass rounded-2xl overflow-hidden">
          <div className="p-6 border-b border-slate-700/50">
            <h2 className="text-lg font-semibold text-white flex items-center">
              <ClipboardList className="w-5 h-5 mr-2 text-indigo-400" />
              Activity History
            </h2>
          </div>
          <div className="divide-y divide-slate-700/50">
            {logs.map((log) => (
              <motion.div 
                key={log.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="p-6"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <span className={`inline-block px-2 py-1 rounded text-xs font-medium ${
                      log.action.includes('CREATE') ? 'bg-green-500/20 text-green-400' :
                      log.action.includes('TX') ? 'bg-indigo-500/20 text-indigo-400' :
                      'bg-slate-700/50 text-slate-300'
                    }`}>
                      {formatAction(log.action)}
                    </span>
                    <p className="text-slate-300 mt-2 text-sm">
                      {JSON.stringify(log.details)}
                    </p>
                  </div>
                  <span className="text-xs text-slate-500">
                    {formatTime(log.timestamp)}
                  </span>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
