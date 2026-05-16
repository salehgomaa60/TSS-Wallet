"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, CheckCircle2, XCircle, Clock, ExternalLink, Loader2, Users } from "lucide-react";
import { api } from "@/lib/api";

interface Transaction {
  id: string;
  to_address: string;
  value_eth: number;
  description: string;
  status: string;
  tx_hash: string | null;
  proposed_at: string;
  expires_at: string;
  proposed_by: { id: string; name: string };
  approvals: any[];
}

export default function TransactionDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [transaction, setTransaction] = useState<Transaction | null>(null);
  const [loading, setLoading] = useState(true);
  const [approving, setApproving] = useState(false);

  useEffect(() => {
    if (params.id) {
      fetchTransaction();
    }
  }, [params.id]);

  const fetchTransaction = async () => {
    try {
      const { data } = await api.get(`/transactions/${params.id}`);
      setTransaction(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    setApproving(true);
    try {
      await api.post(`/transactions/${params.id}/approve`);
      fetchTransaction();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Failed to approve");
    } finally {
      setApproving(false);
    }
  };

  const formatAddress = (addr: string) => {
    return `${addr.slice(0, 6)}...${addr.slice(-4)}`;
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

  if (!transaction) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-slate-400">Transaction not found</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 p-8">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="flex items-center mb-8">
          <button 
            onClick={() => router.push("/dashboard")}
            className="flex items-center text-slate-400 hover:text-white transition-colors mr-4"
          >
            <ArrowLeft className="w-5 h-5 mr-2" />
            Back
          </button>
          <h1 className="text-2xl font-bold text-white">Transaction Details</h1>
        </div>

        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass p-8 rounded-2xl"
        >
          {/* Status Badge */}
          <div className="flex items-center justify-between mb-6">
            <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${
              transaction.status === 'EXECUTED' ? 'bg-green-500/20 text-green-400' :
              transaction.status === 'PENDING' ? 'bg-yellow-500/20 text-yellow-400' :
              transaction.status === 'REJECTED' ? 'bg-red-500/20 text-red-400' :
              'bg-slate-700/50 text-slate-300'
            }`}>
              {transaction.status === 'EXECUTED' && <CheckCircle2 className="w-4 h-4 mr-2" />}
              {transaction.status === 'REJECTED' && <XCircle className="w-4 h-4 mr-2" />}
              {transaction.status === 'PENDING' && <Clock className="w-4 h-4 mr-2" />}
              {transaction.status}
            </span>
            <span className="text-slate-400 text-sm">
              {formatTime(transaction.proposed_at)}
            </span>
          </div>

          {/* Transaction Info */}
          <div className="space-y-6">
            <div>
              <label className="text-sm text-slate-500">Amount</label>
              <p className="text-3xl font-bold text-white">{transaction.value_eth} ETH</p>
            </div>

            <div>
              <label className="text-sm text-slate-500">To</label>
              <p className="font-mono text-indigo-400">{transaction.to_address}</p>
            </div>

            <div>
              <label className="text-sm text-slate-500">Description</label>
              <p className="text-slate-300">{transaction.description}</p>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-4 border-t border-slate-700/50">
              <div>
                <label className="text-sm text-slate-500">Proposed By</label>
                <p className="text-slate-300">{transaction.proposed_by.name}</p>
              </div>
              <div>
                <label className="text-sm text-slate-500">Expires</label>
                <p className="text-slate-300">{formatTime(transaction.expires_at)}</p>
              </div>
            </div>

            {transaction.tx_hash && (
              <div className="pt-4 border-t border-slate-700/50">
                <label className="text-sm text-slate-500">Transaction Hash</label>
                <a 
                  href={`https://sepolia.etherscan.io/tx/${transaction.tx_hash}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center text-indigo-400 hover:text-indigo-300"
                >
                  <span className="font-mono">{formatAddress(transaction.tx_hash)}</span>
                  <ExternalLink className="w-4 h-4 ml-2" />
                </a>
              </div>
            )}
          </div>

          {/* Approvals */}
          <div className="mt-8 pt-6 border-t border-slate-700/50">
            <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
              <Users className="w-5 h-5 mr-2 text-indigo-400" />
              Approvals ({transaction.approvals.length})
            </h3>
            <div className="space-y-3">
              {transaction.approvals.map((approval: any) => (
                <div key={approval.id} className="flex items-center justify-between bg-slate-800/50 p-3 rounded-xl">
                  <div className="flex items-center space-x-3">
                    <div className="w-8 h-8 rounded-full bg-indigo-500/20 flex items-center justify-center">
                      <span className="text-indigo-400 text-sm font-medium">
                        {approval.user.name.split(' ').map((n: string) => n[0]).join('')}
                      </span>
                    </div>
                    <span className="text-slate-300">{approval.user.name}</span>
                  </div>
                  <CheckCircle2 className="w-5 h-5 text-green-400" />
                </div>
              ))}
            </div>
          </div>

          {/* Actions */}
          {transaction.status === 'PENDING' && (
            <div className="mt-8 pt-6 border-t border-slate-700/50">
              <button
                onClick={handleApprove}
                disabled={approving}
                className="w-full bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white rounded-xl px-4 py-3 font-medium transition-all shadow-lg shadow-indigo-500/25 flex items-center justify-center space-x-2"
              >
                {approving ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <><CheckCircle2 className="w-5 h-5" /> <span>Approve Transaction</span></>
                )}
              </button>
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
}
