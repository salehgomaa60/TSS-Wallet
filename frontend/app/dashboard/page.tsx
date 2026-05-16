"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Wallet, Send, RefreshCw, Activity, ArrowUpRight,
  Copy, CheckCircle2, AlertTriangle, Fingerprint,
  ShieldCheck, User,
} from "lucide-react";
import { api } from "@/lib/api";

// ── helpers ────────────────────────────────────────────────────────
function parseSession<T>(key: string): T | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

// ─────────────────────────────────────────────────────────────────
export default function DashboardPage() {
  // Per-session vault info saved at login / signup
  const [vaultInfo, setVaultInfo] = useState<{
    eth_address: string;
    contract_address: string;
    company_name: string;
  } | null>(null);

  const [userInfo, setUserInfo] = useState<{
    email: string;
    full_name: string;
    role: string;
  } | null>(null);

  // Global node-network status (unauthenticated coordinator probe)
  const [networkStatus, setNetworkStatus] = useState<any>(null);
  const [balance, setBalance] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  // Transaction form
  const [toAddress, setToAddress] = useState("");
  const [amount, setAmount] = useState("");
  const [txLoading, setTxLoading] = useState(false);
  const [txResult, setTxResult] = useState<any>(null);

  // ── Load vault & user from THIS tab's localStorage ─────────────
  useEffect(() => {
    const vi = parseSession<typeof vaultInfo>("vault_info");
    const ui = parseSession<typeof userInfo>("user_info");
    setVaultInfo(vi);
    setUserInfo(ui);
  }, []);

  // ── Fetch on-chain balance from coordinator ─────────────────────
  const fetchBalance = async () => {
    try {
      // /wallet/status returns the coordinator's wallet state.
      // Since the backend uses force_new=False, every registered company
      // shares the same DKG snapshot and therefore the same on-chain
      // vault address.  We always show the coordinator's balance — no
      // address comparison needed.
      const { data } = await api.get("/wallet/status");
      setNetworkStatus(data);
      setBalance(data.balance_eth ?? null);

      // If localStorage has no vault address yet (e.g. old session),
      // back-fill it from the coordinator's live status.
      if (!vaultInfo?.eth_address && data.wallet_address) {
        const saved = parseSession<{ eth_address: string; contract_address: string; company_name: string }>("vault_info");
        localStorage.setItem("vault_info", JSON.stringify({
          eth_address:      data.wallet_address,
          contract_address: saved?.contract_address ?? "",
          company_name:     saved?.company_name     ?? "",
        }));
        setVaultInfo(v => ({
          eth_address:      data.wallet_address,
          contract_address: v?.contract_address ?? "",
          company_name:     v?.company_name     ?? "",
        }));
      }
    } catch {
      // Coordinator offline — show cached vault info without balance
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBalance();
    const interval = setInterval(fetchBalance, 15000);
    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const walletAddr = vaultInfo?.eth_address || networkStatus?.wallet_address;

  const handleCopy = () => {
    if (walletAddr) {
      navigator.clipboard.writeText(walletAddr);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!toAddress || !amount) return;

    setTxLoading(true);
    setTxResult(null);
    try {
      const amountWei = Math.floor(parseFloat(amount) * 1e18);
      const { data } = await api.post("/wallet/sign", {
        to_address: toAddress,
        value_wei: amountWei,
        participating_nodes: [1, 2, 3],
        broadcast: true,
      });
      setTxResult(data);
      setToAddress("");
      setAmount("");
      fetchBalance();
    } catch (err: any) {
      setTxResult({ error: err.response?.data?.detail || "Transaction failed" });
    } finally {
      setTxLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <RefreshCw className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-6xl mx-auto space-y-8 pb-20">

      {/* Header */}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-bold text-white tracking-tight">Overview</h1>
          <p className="text-slate-400 mt-1">
            {vaultInfo?.company_name
              ? `${vaultInfo.company_name} — MPC Vault`
              : "Manage your distributed MPC wallet assets"}
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {/* Session badge — shows which user is logged in THIS tab */}
          {userInfo && (
            <div className="flex items-center space-x-2 px-3 py-1.5 bg-slate-800/60 border border-slate-700/50 rounded-full text-xs text-slate-400">
              <User className="w-3.5 h-3.5" />
              <span>{userInfo.email}</span>
            </div>
          )}
          <button
            onClick={fetchBalance}
            className="p-2 rounded-full hover:bg-slate-800 text-slate-400 hover:text-white transition-all"
          >
            <RefreshCw className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Top Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* Balance Card — always shows THIS user's vault address */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="glass rounded-2xl p-6 lg:col-span-2 relative overflow-hidden group"
        >
          <div className="absolute -right-20 -top-20 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl group-hover:bg-indigo-500/20 transition-all duration-700" />

          <div className="flex items-center space-x-3 mb-6">
            <div className="p-2.5 bg-indigo-500/20 rounded-xl">
              <Wallet className="w-6 h-6 text-indigo-400" />
            </div>
            <h2 className="text-lg font-semibold text-slate-200">Sepolia Balance</h2>
          </div>

          <div className="flex flex-col">
            <span className="text-5xl font-black text-white tracking-tight">
              {balance !== null ? balance : "—"}{" "}
              <span className="text-2xl text-slate-400 font-semibold">ETH</span>
            </span>
            <div className="mt-6 flex items-center space-x-2 bg-slate-900/50 inline-flex w-fit px-4 py-2 rounded-lg border border-slate-700/50">
              <span className="font-mono text-slate-300 text-sm">
                {walletAddr
                  ? `${walletAddr.substring(0, 6)}...${walletAddr.substring(38)}`
                  : "Not Initialized"}
              </span>
              {walletAddr && (
                <button onClick={handleCopy} className="text-slate-400 hover:text-white transition-colors ml-2">
                  {copied
                    ? <CheckCircle2 className="w-4 h-4 text-green-400" />
                    : <Copy className="w-4 h-4" />}
                </button>
              )}
            </div>
          </div>
        </motion.div>

        {/* Node Network Status */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
          className="glass rounded-2xl p-6 flex flex-col"
        >
          <div className="flex items-center space-x-3 mb-4">
            <div className="p-2.5 bg-purple-500/20 rounded-xl">
              <Activity className="w-6 h-6 text-purple-400" />
            </div>
            <h2 className="text-lg font-semibold text-slate-200">Network Status</h2>
          </div>

          <div className="flex-1 flex flex-col justify-center">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-slate-400">Threshold Setup</span>
              <span className="text-sm font-semibold text-white">
                {networkStatus?.threshold} of {networkStatus?.total_nodes}
              </span>
            </div>

            <div className="grid grid-cols-5 gap-2 mt-4">
              {[1, 2, 3, 4, 5].map((node) => {
                const isActive = networkStatus?.active_nodes?.includes(node);
                return (
                  <div key={node} className="flex flex-col items-center space-y-2">
                    <div className={`w-3 h-3 rounded-full ${isActive ? "bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.5)]" : "bg-slate-700"}`} />
                    <span className="text-xs text-slate-500">N{node}</span>
                  </div>
                );
              })}
            </div>

            {networkStatus?.snapshot_exists ? (
              <div className="mt-6 flex items-center space-x-2 text-xs text-green-400 bg-green-400/10 px-3 py-2 rounded-lg border border-green-400/20">
                <ShieldCheck className="w-4 h-4" />
                <span>DKG Snapshot Active</span>
              </div>
            ) : (
              <div className="mt-6 flex items-center space-x-2 text-xs text-amber-400 bg-amber-400/10 px-3 py-2 rounded-lg border border-amber-400/20">
                <AlertTriangle className="w-4 h-4" />
                <span>No Snapshot Found</span>
              </div>
            )}
          </div>
        </motion.div>
      </div>

      {/* Action Area */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Send ETH Form */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          className="glass rounded-2xl p-6 relative"
        >
          <div className="flex items-center space-x-3 mb-6">
            <div className="p-2.5 bg-blue-500/20 rounded-xl">
              <Send className="w-6 h-6 text-blue-400" />
            </div>
            <h2 className="text-lg font-semibold text-slate-200">Send Ethereum</h2>
          </div>

          <form onSubmit={handleSend} className="space-y-4">
            <div>
              <label className="block text-sm text-slate-400 mb-1">Recipient Address</label>
              <input
                type="text"
                required
                value={toAddress}
                onChange={(e) => setToAddress(e.target.value)}
                className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all placeholder:text-slate-600 font-mono text-sm"
                placeholder="0x..."
              />
            </div>
            <div>
              <label className="block text-sm text-slate-400 mb-1">Amount (ETH)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.000000000000000001"
                  required
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="w-full bg-slate-900/50 border border-slate-700/50 rounded-xl pl-4 pr-16 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all placeholder:text-slate-600 font-medium"
                  placeholder="0.01"
                />
                <div className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 font-semibold text-sm">
                  ETH
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={txLoading || !walletAddr || !networkStatus?.has_wallet}
              className="w-full mt-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-medium py-3.5 rounded-xl shadow-lg shadow-blue-500/25 transition-all flex items-center justify-center space-x-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {txLoading ? (
                <><RefreshCw className="w-5 h-5 animate-spin" /> <span>Signing via MPC...</span></>
              ) : (
                <><Fingerprint className="w-5 h-5" /> <span>Sign &amp; Broadcast</span></>
              )}
            </button>
          </form>
        </motion.div>

        {/* Transaction Result */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
          className="glass rounded-2xl p-6"
        >
          <div className="flex items-center space-x-3 mb-6">
            <div className="p-2.5 bg-green-500/20 rounded-xl">
              <ArrowUpRight className="w-6 h-6 text-green-400" />
            </div>
            <h2 className="text-lg font-semibold text-slate-200">Transaction Status</h2>
          </div>

          <div className="flex-1 flex flex-col items-center justify-center h-[250px]">
            {!txResult ? (
              <div className="text-center text-slate-500">
                <Fingerprint className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p>Propose a transaction to initiate <br />Threshold Signature protocol</p>
              </div>
            ) : txResult.error ? (
              <div className="w-full p-4 bg-red-500/10 border border-red-500/20 rounded-xl">
                <div className="flex items-center space-x-2 text-red-400 font-semibold mb-2">
                  <AlertTriangle className="w-5 h-5" />
                  <span>Transaction Failed</span>
                </div>
                <p className="text-slate-300 text-sm">{txResult.error}</p>
              </div>
            ) : (
              <div className="w-full space-y-4">
                <div className="p-4 bg-green-500/10 border border-green-500/20 rounded-xl">
                  <div className="flex items-center space-x-2 text-green-400 font-semibold mb-2">
                    <CheckCircle2 className="w-5 h-5" />
                    <span>MPC Signature Verified</span>
                  </div>
                  <p className="text-slate-300 text-sm mb-1">
                    Nodes participated:{" "}
                    <span className="font-mono text-indigo-300">
                      {txResult.participating_nodes?.join(", ")}
                    </span>
                  </p>
                  {txResult.broadcast?.tx_hash && (
                    <div className="mt-3 text-xs bg-black/30 p-2 rounded border border-slate-800 overflow-hidden text-ellipsis whitespace-nowrap">
                      <span className="text-slate-500">Hash: </span>
                      <a
                        href={txResult.broadcast.etherscan_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-400 hover:underline font-mono"
                      >
                        {txResult.broadcast.tx_hash}
                      </a>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </div>
  );
}
