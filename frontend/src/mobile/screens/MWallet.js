import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowDownCircle, ArrowUpCircle, FileText, PlusCircle } from "lucide-react";
import mobileApi from "@/mobile/api/client";
import { useShell } from "@/mobile/MobileShell";
import {
  Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, StatusPill, Segmented, useAsync,
} from "@/mobile/ui/kit";

const TABS = [["transactions", "الحركات"], ["topups", "طلبات الشحن"], ["withdrawals", "السحوبات"]];
const CURRENCIES = [["SAR", "ريال سعودي"], ["USD", "دولار أمريكي"]];

export default function MWallet() {
  const navigate = useNavigate();
  const { wallet, features, reload: reloadShell } = useShell();
  const [cur, setCur] = useState("SAR");
  const [tab, setTab] = useState("transactions");
  const data = useAsync(() => (
    tab === "topups" ? mobileApi.topups()
      : tab === "withdrawals" ? mobileApi.withdrawals().catch(() => [])
      : mobileApi.transactions()
  ), [tab], { cacheKey: `m-wallet-${tab}` });

  const tabs = TABS.filter(([k]) => k !== "withdrawals" || features.withdrawals);
  const refresh = async () => { await Promise.all([reloadShell(), data.reload()]); };

  return (
    <Screen refresh={refresh}>
      <TopBar title="المحفظة" subtitle="نفس محفظة معراج — بلا أي رصيد موازٍ"
              right={<button onClick={refresh} data-testid="m-wallet-refresh" aria-label="تحديث"
                             className="text-[11px] font-bold text-white/70 px-2 py-1">تحديث</button>} />

      {/* balance card with currency switcher */}
      <div className="px-4 pt-4">
        <div className="rounded-[26px] bg-[#0A2540] text-white p-5 relative overflow-hidden shadow-[0_14px_30px_-18px_rgba(10,37,64,1)]"
             data-testid={`m-wallet-${cur}`}>
          <div className="absolute -bottom-14 -end-8 w-44 h-44 rounded-full bg-[#D4AF37]/10" />
          <div className="relative flex items-center gap-2">
            {CURRENCIES.map(([c, label]) => (
              <button key={c} onClick={() => setCur(c)} data-testid={`m-wallet-cur-${c}`}
                      className={`h-9 px-3.5 rounded-full text-[11px] font-bold transition-colors ${
                        cur === c ? "bg-[#D4AF37] text-[#0A2540]" : "bg-white/10 text-white/70"}`}>
                {label}
              </button>
            ))}
          </div>
          <p className="relative text-[11px] text-white/55 font-semibold mt-5">الرصيد المتاح</p>
          <p className="relative text-[32px] leading-tight mt-1">
            <Money value={wallet?.[cur]?.available} currency={cur} />
          </p>
          <p className="relative text-[11px] text-white/50 mt-2">
            معلّق: <Money value={wallet?.[cur]?.pending} currency={cur} />
          </p>
          <div className="relative grid grid-cols-2 gap-3 mt-5">
            <button onClick={() => navigate("/m/wallet/topup")} data-testid="m-wallet-topup"
                    className="h-12 rounded-2xl bg-[#D4AF37] text-[#0A2540] text-xs font-bold flex items-center justify-center gap-1.5 active:scale-95 transition-transform">
              <PlusCircle className="w-4 h-4" /> شحن الرصيد
            </button>
            <button onClick={() => navigate("/m/statement")} data-testid="m-wallet-statement"
                    className="h-12 rounded-2xl bg-white/10 text-white text-xs font-bold flex items-center justify-center gap-1.5 active:scale-95 transition-transform">
              <FileText className="w-4 h-4" /> كشف الحساب
            </button>
          </div>
        </div>
      </div>

      <div className="px-4 pt-5">
        <Segmented items={tabs} value={tab} onChange={setTab} testid="m-wallet-tabs" testidPrefix="m-wallet-tab-" />
      </div>

      {data.loading ? <Skeleton rows={4} />
        : data.error ? <ErrorState message={data.error} onRetry={data.reload} />
        : (data.data || []).length === 0 ? <EmptyState title="لا سجلات" hint="ستظهر هنا كل حركاتك المالية" />
        : (
          <div className="p-4 space-y-3 m-stagger" data-testid="m-wallet-list">
            {data.data.map((r) => {
              const amount = Number(r.amount || 0);
              const inflow = tab === "transactions" ? amount >= 0 : tab === "topups";
              return (
                <Card key={r.id} testid={`m-wallet-row-${r.id}`}>
                  <div className="flex items-center gap-3">
                    <span className={`w-11 h-11 rounded-2xl flex items-center justify-center shrink-0 ${
                      inflow ? "bg-emerald-50" : "bg-red-50"}`}>
                      {inflow ? <ArrowDownCircle className="w-5 h-5 text-emerald-600" />
                        : <ArrowUpCircle className="w-5 h-5 text-red-600" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-bold text-[#0A2540] truncate">
                        {r.description || r.method || r.type || "حركة"}
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        {String(r.created_at || "").slice(0, 16).replace("T", " ")}
                      </p>
                    </div>
                    <div className="text-end shrink-0">
                      <div className={`text-sm ${inflow ? "text-emerald-700" : "text-red-700"}`}>
                        <Money value={Math.abs(amount)} currency={r.currency} />
                      </div>
                      {r.status && <div className="mt-1.5"><StatusPill status={r.status} /></div>}
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
    </Screen>
  );
}
