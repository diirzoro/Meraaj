import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowDownCircle, ArrowUpCircle, PlusCircle } from "lucide-react";
import mobileApi from "@/mobile/api/client";
import { useShell } from "@/mobile/MobileShell";
import { Screen, TopBar, Card, Skeleton, ErrorState, EmptyState, Money, StatusPill, useAsync } from "@/mobile/ui/kit";

const TABS = [["transactions", "الحركات"], ["topups", "طلبات الشحن"], ["withdrawals", "السحوبات"]];

export default function MWallet() {
  const navigate = useNavigate();
  const { wallet, features, reload: reloadShell } = useShell();
  const [tab, setTab] = useState("transactions");
  const data = useAsync(() => (
    tab === "topups" ? mobileApi.topups()
      : tab === "withdrawals" ? mobileApi.withdrawals().catch(() => [])
      : mobileApi.transactions()
  ), [tab]);

  const tabs = TABS.filter(([k]) => k !== "withdrawals" || features.withdrawals);

  return (
    <Screen>
      <TopBar title="المحفظة" subtitle="نفس محفظة معراج — بلا أي رصيد موازٍ"
              right={<button onClick={() => { reloadShell(); data.reload(); }} data-testid="m-wallet-refresh"
                             className="text-[11px] font-semibold text-white/70">تحديث</button>} />

      <div className="p-4 grid grid-cols-2 gap-3">
        {["SAR", "USD"].map((c) => (
          <Card key={c} testid={`m-wallet-${c}`}>
            <p className="text-[11px] text-muted-foreground">{c === "SAR" ? "ريال سعودي" : "دولار أمريكي"}</p>
            <p className="text-lg mt-1"><Money value={wallet?.[c]?.available} currency={c} /></p>
            <p className="text-[11px] text-muted-foreground mt-1">
              معلّق: <Money value={wallet?.[c]?.pending} />
            </p>
          </Card>
        ))}
      </div>

      <div className="px-4 grid grid-cols-2 gap-3">
        <button onClick={() => navigate("/m/wallet/topup")} data-testid="m-wallet-topup"
                className="h-12 rounded-xl bg-[#D4AF37] text-[#0A2540] text-sm font-bold flex items-center justify-center gap-2 active:scale-95 transition-transform">
          <PlusCircle className="w-4 h-4" /> شحن الرصيد
        </button>
        <button onClick={() => navigate("/m/statement")} data-testid="m-wallet-statement"
                className="h-12 rounded-xl bg-white border text-[#0A2540] text-sm font-semibold flex items-center justify-center gap-2">
          كشف الحساب
        </button>
      </div>

      <div className="px-4 pt-5 flex gap-2" data-testid="m-wallet-tabs">
        {tabs.map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`m-wallet-tab-${k}`}
                  className={`h-10 px-4 rounded-full text-xs font-bold ${tab === k ? "bg-[#0A2540] text-white" : "bg-white border text-[#0A2540]"}`}>
            {l}
          </button>
        ))}
      </div>

      {data.loading ? <Skeleton rows={4} />
        : data.error ? <ErrorState message={data.error} onRetry={data.reload} />
        : (data.data || []).length === 0 ? <EmptyState title="لا سجلات" />
        : (
          <div className="p-4 space-y-3" data-testid="m-wallet-list">
            {data.data.map((r) => {
              const amount = Number(r.amount || 0);
              const inflow = tab === "transactions" ? amount >= 0 : tab === "topups";
              return (
                <Card key={r.id} testid={`m-wallet-row-${r.id}`}>
                  <div className="flex items-center gap-3">
                    <span className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${inflow ? "bg-emerald-50" : "bg-red-50"}`}>
                      {inflow ? <ArrowDownCircle className="w-5 h-5 text-emerald-600" />
                        : <ArrowUpCircle className="w-5 h-5 text-red-600" />}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold text-[#0A2540] truncate">
                        {r.description || r.method || r.type || "حركة"}
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        {String(r.created_at || "").slice(0, 16).replace("T", " ")}
                      </p>
                    </div>
                    <div className="text-end shrink-0">
                      <div className="text-xs"><Money value={Math.abs(amount)} currency={r.currency} /></div>
                      {r.status && <div className="mt-1"><StatusPill status={r.status} /></div>}
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
