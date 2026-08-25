import { Link, useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import api from "@/lib/api";
import { money, fmtDate, PKG_TYPE, roomCustomer } from "@/lib/format";
import { PkgImage } from "@/components/PkgImage";
import { Button } from "@/components/ui/button";
import {
  Network, Store, Wallet, ShieldCheck, ArrowLeft, CheckCircle2,
  Building2, RefreshCw, TrendingUp, Lock, Users, Sparkles, CalendarDays, MapPin,
} from "lucide-react";

const HERO = "https://images.unsplash.com/photo-1592326871020-04f58c1a52f3?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1MDZ8MHwxfHNlYXJjaHwxfHxLYWFiYSUyME1lY2NhJTIwcGlsZ3JpbWFnZSUyMGNyb3dkfGVufDB8fHx8MTc4NzI0OTU0Mnww&ixlib=rb-4.1.0&q=85";
const TOURISM = "https://images.unsplash.com/photo-1527838832700-5059252407fa?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1MTN8MHwxfHNlYXJjaHwxfHxJc3RhbmJ1bCUyMG1vc3F1ZSUyMHRyYXZlbCUyMHRvdXJpc218ZW58MHx8fHwxNzg3MjQ5NTQyfDA&ixlib=rb-4.1.0&q=85";

const features = [
  { icon: Store, title: "سوق B2B موحّد", desc: "منصة واحدة تعرض فيها برامج العمرة والسياحة وتشتري من مكاتب أخرى بضغطة زر." },
  { icon: Wallet, title: "محافظ مسبقة الدفع", desc: "محفظة لكل مكتب بأرصدة (إجمالي، معلّق، متاح) تضبط كل عملية بيع وشراء بدقّة." },
  { icon: ShieldCheck, title: "نظام ضمان (Escrow)", desc: "تبقى أموال الحجز معلّقة حتى إتمام التفويج، فلا يخسر البائع ولا المشتري." },
  { icon: RefreshCw, title: "تكامل مع نظام رحال", desc: "شارك برامجك من رحال إلى السوق فوراً، مع تزامن لحظي للمقاعد ومنع البيع المزدوج." },
];

const steps = [
  { n: "١", title: "سجّل مكتبك", desc: "أنشئ حساب مكتبك ببياناتك الكاملة وابدأ خلال دقائق." },
  { n: "٢", title: "اشحن محفظتك", desc: "ارفع إشعار الحوالة البنكية وتعتمده الإدارة ليصبح رصيدك جاهزاً." },
  { n: "٣", title: "بِع واشترِ", desc: "اعرض برامجك أو احجز من السوق، والنظام يدير الضمان والعمولات تلقائياً." },
];

const lifecycle = [
  { c: "#1D4ED8", bg: "#EFF6FF", b: "#BFDBFE", t: "قيد التسجيل", d: "تجميد الرصيد ورفع أسماء المعتمرين وبيانات الجوازات." },
  { c: "#A16207", bg: "#FEFCE8", b: "#FEF08A", t: "تم إصدار التأشيرات", d: "إدخال رقم التأشيرة لكل مسجّل ورفع ملفاتها للطباعة." },
  { c: "#15803D", bg: "#F0FDF4", b: "#BBF7D0", t: "تم التفويج", d: "مهلة اعتراض 24 ساعة ثم تحويل الرصيد المعلّق إلى متاح." },
];

export default function Landing() {
  const navigate = useNavigate();
  const [programs, setPrograms] = useState([]);
  useEffect(() => {
    const ref = new URLSearchParams(window.location.search).get("ref");
    if (ref) localStorage.setItem("meraaj_ref", ref);
    api.get("/packages").then((r) => setPrograms((r.data || []).slice(0, 6))).catch(() => {});
  }, []);
  return (
    <div className="min-h-screen bg-[#F4F6F8]" dir="rtl">
      {/* Nav */}
      <header className="fixed top-0 inset-x-0 z-40 bg-[#0A2540]/95 backdrop-blur border-b border-white/10">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-[#D4AF37] flex items-center justify-center"><Network className="w-5 h-5 text-[#0A2540]" /></div>
            <div className="text-white">
              <div className="font-head font-bold leading-tight">معراج نتورك</div>
              <div className="text-[10px] text-white/50">Meraaj Network</div>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <Button variant="ghost" data-testid="nav-login-btn" onClick={() => navigate("/login")}
                    className="text-white hover:bg-white/10 hover:text-white h-9">تسجيل الدخول</Button>
            <Button data-testid="nav-register-btn" onClick={() => navigate("/register")}
                    className="bg-[#D4AF37] hover:bg-[#c39f2f] text-[#0A2540] font-semibold h-9">إنشاء حساب</Button>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative bg-[#0A2540] text-white overflow-hidden pt-16">
        <div className="absolute -top-32 -start-32 w-[28rem] h-[28rem] rounded-full bg-[#D4AF37]/10 blur-3xl" />
        <div className="max-w-6xl mx-auto px-5 sm:px-8 grid lg:grid-cols-2 gap-12 items-center py-16 lg:py-24 relative">
          <div className="animate-fade-up">
            <span className="inline-flex items-center gap-2 bg-white/5 border border-white/10 rounded-full px-4 py-1.5 text-xs text-[#D4AF37] mb-6">
              <Sparkles className="w-3.5 h-3.5" /> منصة تابعة لشركة Target Media
            </span>
            <h1 className="font-head text-4xl sm:text-5xl lg:text-6xl font-bold leading-[1.15] mb-6">
              سوق <span className="text-[#D4AF37]">موحّد</span> لتبادل برامج<br /> العمرة والسياحة
            </h1>
            <p className="text-white/60 text-base sm:text-lg leading-relaxed max-w-lg mb-8">
              منصة تجمع المكاتب والأفراد والمسوّقين: بِع واشترِ واحجز برامج العمرة والسياحة بنظام محافظ مسبقة الدفع وضمان مالي كامل يحمي الجميع.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button data-testid="hero-register-btn" onClick={() => navigate("/register")}
                      className="bg-[#D4AF37] hover:bg-[#c39f2f] text-[#0A2540] font-semibold h-12 px-7 text-base">
                إنشاء حساب جديد <ArrowLeft className="w-4 h-4" />
              </Button>
              <Button data-testid="hero-login-btn" variant="outline" onClick={() => navigate("/login")}
                      className="h-12 px-7 text-base bg-transparent border-white/20 text-white hover:bg-white/10 hover:text-white">
                تسجيل الدخول
              </Button>
            </div>
            <div className="flex flex-wrap gap-x-8 gap-y-3 mt-10 text-sm text-white/60">
              {["بدون بوابات دفع معقّدة", "محافظ وضمان مالي", "تكامل مع نظام رحال"].map((t) => (
                <span key={t} className="flex items-center gap-2"><CheckCircle2 className="w-4 h-4 text-[#D4AF37]" /> {t}</span>
              ))}
            </div>
          </div>

          <div className="relative animate-fade-up" style={{ animationDelay: "0.15s" }}>
            <div className="rounded-3xl overflow-hidden border border-white/10 shadow-2xl">
              <img src={HERO} alt="العمرة" className="w-full h-[420px] object-cover" />
            </div>
            <div className="absolute -bottom-6 -start-6 bg-white rounded-2xl p-5 shadow-xl w-56 hidden sm:block">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-xl bg-[#F0FDF4] flex items-center justify-center"><TrendingUp className="w-5 h-5 text-[#15803D]" /></div>
                <div className="text-xs text-muted-foreground">رصيد متاح</div>
              </div>
              <div className="tabular text-2xl font-bold text-[#0A2540]">$12,450</div>
              <div className="text-[11px] text-[#15803D] mt-1">جاهز للسحب أو الشراء</div>
            </div>
          </div>
        </div>
      </section>

      {/* Latest programs (public browsing) */}
      {programs.length > 0 && (
        <section className="max-w-6xl mx-auto px-5 sm:px-8 py-20" data-testid="landing-programs">
          <div className="flex items-end justify-between mb-10 gap-4 flex-wrap">
            <div>
              <h2 className="font-head text-3xl sm:text-4xl font-bold text-[#0A2540] mb-3">أحدث البرامج المتاحة</h2>
              <p className="text-muted-foreground">تصفّح أحدث عروض العمرة والسياحة من المكاتب — دون تسجيل دخول.</p>
            </div>
            <Button variant="outline" onClick={() => navigate("/market")} data-testid="landing-view-all-btn"
                    className="border-[#0A2540] text-[#0A2540] hover:bg-[#0A2540]/5 h-11 px-6">
              تصفّح كل البرامج <ArrowLeft className="w-4 h-4" />
            </Button>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {programs.map((p) => {
              const rooms = Array.isArray(p.room_pricing) ? p.room_pricing : [];
              const adults = rooms.map((r) => roomCustomer(r?.customer, "adult")).filter((v) => v != null && !isNaN(v) && v > 0);
              const start = adults.length ? Math.min(...adults) : (Number(p.final_sale_price) || 0);
              return (
                <Link key={p.id} to={`/market/${p.id}`} data-testid={`landing-pkg-${p.id}`}
                      className="hover-lift bg-white rounded-2xl border overflow-hidden card-shadow group">
                  <div className="aspect-[4/3] bg-[#0A2540] relative overflow-hidden">
                    <PkgImage src={p.images?.[0]} alt={p.title} />
                    <span className="absolute top-3 start-3 bg-white/90 text-[#0A2540] text-xs font-semibold px-3 py-1 rounded-full">{PKG_TYPE[p.type] || p.type}</span>
                  </div>
                  <div className="p-5">
                    <h3 className="font-head font-bold text-[#0A2540] line-clamp-1">{p.title}</h3>
                    <p className="text-xs text-muted-foreground mt-1">{p.seller_office_name}</p>
                    <div className="flex flex-wrap gap-3 mt-3 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1"><CalendarDays className="w-3.5 h-3.5" /> {fmtDate(p.departure_date)}</span>
                      <span className="flex items-center gap-1"><MapPin className="w-3.5 h-3.5" /> {p.departure_city || "-"}</span>
                      <span className={`flex items-center gap-1 font-semibold ${p.is_full ? "text-[#DC2626]" : "text-[#15803D]"}`}><Users className="w-3.5 h-3.5" /> {p.is_full ? "ممتلئ" : "متاح"}</span>
                    </div>
                    <div className="mt-4 pt-4 border-t">
                      <div className="text-[11px] text-muted-foreground">{adults.length ? "يبدأ من" : "سعر البيع للزبون"}</div>
                      <div className="flex items-center gap-2">
                        <div className="tabular text-xl font-bold text-[#0A2540]">{money(start, p.currency)}</div>
                        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${p.currency === "USD" ? "bg-[#ECFDF5] text-[#047857]" : "bg-[#EFF6FF] text-[#1D4ED8]"}`}>{p.currency === "USD" ? "USD" : "SAR"}</span>
                      </div>
                    </div>
                  </div>
                </Link>
              );
            })}
          </div>
        </section>
      )}

      {/* Features */}
      <section className="max-w-6xl mx-auto px-5 sm:px-8 py-20">
        <div className="text-center max-w-2xl mx-auto mb-14">
          <h2 className="font-head text-3xl sm:text-4xl font-bold text-[#0A2540] mb-4">كل ما تحتاجه في مكان واحد</h2>
          <p className="text-muted-foreground">منصة متكاملة للمكاتب والأفراد والمسوّقين في اليمن والمنطقة.</p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((f, i) => (
            <div key={i} className="hover-lift bg-white rounded-2xl border p-6 card-shadow" data-testid={`feature-${i}`}>
              <div className="w-12 h-12 rounded-xl bg-[#0A2540] flex items-center justify-center mb-5"><f.icon className="w-6 h-6 text-[#D4AF37]" /></div>
              <h3 className="font-head font-bold text-[#0A2540] mb-2">{f.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Unified account */}
      <section className="bg-white border-y">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 py-20 grid lg:grid-cols-2 gap-12 items-center">
          <div className="rounded-3xl overflow-hidden border card-shadow order-2 lg:order-1">
            <img src={TOURISM} alt="سياحة" className="w-full h-[360px] object-cover" />
          </div>
          <div className="order-1 lg:order-2">
            <span className="inline-flex items-center gap-2 bg-[#F4F6F8] rounded-full px-4 py-1.5 text-xs text-[#0A2540] font-semibold mb-5">
              <Building2 className="w-3.5 h-3.5" /> حساب واحد موحّد
            </span>
            <h2 className="font-head text-3xl sm:text-4xl font-bold text-[#0A2540] mb-5">بائع ومشترٍ… بنفس الحساب والمحفظة</h2>
            <p className="text-muted-foreground leading-relaxed mb-6">
              لا حاجة لحسابات منفصلة. مكتبك يعرض برامجه ويحجز من الآخرين عبر داشبورد واحد، والنظام يحدّد طبيعة كل عملية برمجياً.
            </p>
            <div className="space-y-3">
              {[
                [Store, "أدوات البيع: عرض البرامج، متابعة الحجوزات الواردة، وطلبات السحب."],
                [Wallet, "أدوات الشراء: تصفّح السوق بالفلاتر، الحجز، وشحن المحفظة."],
                [Lock, "ضمان مالي يحمي كل صفقة حتى إتمام التفويج."],
              ].map(([Icon, t], i) => (
                <div key={i} className="flex items-start gap-3">
                  <div className="w-9 h-9 rounded-lg bg-[#F4F6F8] flex items-center justify-center shrink-0"><Icon className="w-4 h-4 text-[#0A2540]" /></div>
                  <p className="text-sm text-[#0A2540] pt-1.5">{t}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="max-w-6xl mx-auto px-5 sm:px-8 py-20">
        <div className="text-center mb-14">
          <h2 className="font-head text-3xl sm:text-4xl font-bold text-[#0A2540]">ابدأ في ثلاث خطوات</h2>
        </div>
        <div className="grid md:grid-cols-3 gap-6">
          {steps.map((s, i) => (
            <div key={i} className="relative bg-white rounded-2xl border p-8 card-shadow" data-testid={`step-${i}`}>
              <div className="w-12 h-12 rounded-full bg-[#0A2540] text-[#D4AF37] font-head font-bold text-xl flex items-center justify-center mb-5">{s.n}</div>
              <h3 className="font-head font-bold text-[#0A2540] mb-2 text-lg">{s.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Lifecycle */}
      <section className="bg-white border-y">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 py-20">
          <div className="text-center max-w-2xl mx-auto mb-14">
            <h2 className="font-head text-3xl sm:text-4xl font-bold text-[#0A2540] mb-4">دورة حجز واضحة بثلاث حالات</h2>
            <p className="text-muted-foreground">تتبّع كل حجز بألوان دالّة من التسجيل حتى تحرير الرصيد.</p>
          </div>
          <div className="grid md:grid-cols-3 gap-6">
            {lifecycle.map((l, i) => (
              <div key={i} className="rounded-2xl border p-6" style={{ background: l.bg, borderColor: l.b }} data-testid={`lifecycle-${i}`}>
                <div className="flex items-center gap-2 mb-3">
                  <span className="w-3 h-3 rounded-full" style={{ background: l.c }} />
                  <span className="font-head font-bold" style={{ color: l.c }}>{l.t}</span>
                </div>
                <p className="text-sm leading-relaxed" style={{ color: l.c }}>{l.d}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* For individuals & marketers */}
      <section className="max-w-6xl mx-auto px-5 sm:px-8 py-20">
        <div className="text-center max-w-2xl mx-auto mb-12">
          <h2 className="font-head text-3xl sm:text-4xl font-bold text-[#0A2540] mb-4">لست مكتباً؟ لدينا مكانك أيضاً</h2>
          <p className="text-muted-foreground">احجز رحلتك مباشرةً، أو انضم كمسوّق واكسب عمولة على كل حجز عبر رابطك.</p>
        </div>
        <div className="grid md:grid-cols-2 gap-6">
          <div className="rounded-2xl border p-8 card-shadow bg-white" data-testid="b2c-consumer">
            <div className="w-12 h-12 rounded-xl bg-[#0A2540] flex items-center justify-center mb-5"><Users className="w-6 h-6 text-[#D4AF37]" /></div>
            <h3 className="font-head font-bold text-[#0A2540] text-xl mb-2">للمستهلك الفرد</h3>
            <p className="text-sm text-muted-foreground leading-relaxed mb-5">تصفّح برامج العمرة والسياحة واحجز بسعر واضح ونهائي، مع ضمان مالي يحمي أموالك حتى إتمام الرحلة.</p>
            <Button variant="outline" onClick={() => navigate("/register")} data-testid="b2c-consumer-btn" className="border-[#0A2540] text-[#0A2540] hover:bg-[#0A2540]/5">ابدأ الحجز الآن</Button>
          </div>
          <div className="rounded-2xl border p-8 card-shadow bg-[#0A2540] text-white" data-testid="b2c-marketer">
            <div className="w-12 h-12 rounded-xl bg-[#D4AF37] flex items-center justify-center mb-5"><TrendingUp className="w-6 h-6 text-[#0A2540]" /></div>
            <h3 className="font-head font-bold text-xl mb-2">للمسوّق بالعمولة</h3>
            <p className="text-sm text-white/60 leading-relaxed mb-5">فعّل وضع المسوّق واحصل على رابط إحالة خاص بك. كل حجز يتم عبر رابطك يمنحك عمولة تحفيزية تُضاف إلى محفظتك.</p>
            <Button onClick={() => navigate("/register")} data-testid="b2c-marketer-btn" className="bg-[#D4AF37] hover:bg-[#c39f2f] text-[#0A2540] font-semibold">انضم كمسوّق</Button>
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-6xl mx-auto px-5 sm:px-8 py-20">
        <div className="relative bg-[#0A2540] rounded-3xl overflow-hidden px-8 py-16 text-center">
          <div className="absolute -top-24 -end-24 w-80 h-80 rounded-full bg-[#D4AF37]/10 blur-3xl" />
          <div className="relative">
            <Users className="w-10 h-10 text-[#D4AF37] mx-auto mb-5" />
            <h2 className="font-head text-3xl sm:text-4xl font-bold text-white mb-4">انضم إلى شبكة معراج اليوم</h2>
            <p className="text-white/60 max-w-lg mx-auto mb-8">أنشئ حساب مكتبك مجاناً وابدأ بتبادل البرامج بأمان مع المكاتب الأخرى.</p>
            <Button data-testid="cta-register-btn" onClick={() => navigate("/register")}
                    className="bg-[#D4AF37] hover:bg-[#c39f2f] text-[#0A2540] font-semibold h-12 px-8 text-base">
              إنشاء حساب مكتب <ArrowLeft className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-[#0A2540] text-white/50">
        <div className="max-w-6xl mx-auto px-5 sm:px-8 py-10 flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#D4AF37] flex items-center justify-center"><Network className="w-4 h-4 text-[#0A2540]" /></div>
            <span className="text-white font-head font-bold">معراج نتورك</span>
          </div>
          <div className="flex items-center gap-6 text-sm">
            <Link to="/login" className="hover:text-white">تسجيل الدخول</Link>
            <Link to="/register" className="hover:text-white">إنشاء حساب</Link>
          </div>
          <div className="text-xs">© 2026 Target Media — جميع الحقوق محفوظة</div>
        </div>
      </footer>
    </div>
  );
}
