import { useState } from "react";
import { useNavigate } from "react-router-dom";
import api, { apiError } from "@/lib/api";
import { PageHeader } from "@/components/Layout";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Plus, Trash2 } from "lucide-react";
import { money } from "@/lib/format";
import { optimizeImage } from "@/lib/imageOptimizer";
import { toast } from "sonner";

const IMG = {
  umrah: "https://images.unsplash.com/photo-1693590614566-1d3ea9ef32f7?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1Nzd8MHwxfHNlYXJjaHwzfHxNZWNjYSUyMEthYWJhJTIwVW1yYWh8ZW58MHx8fHwxNzg3MjI1MTg4fDA&ixlib=rb-4.1.0&q=85",
  tourism: "https://images.pexels.com/photos/18417462/pexels-photo-18417462.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
};

export default function CreatePackage() {
  const navigate = useNavigate();
  const [f, setF] = useState({
    type: "umrah", title: "", description: "", departure_date: "", return_date: "",
    departure_city: "", transport: "", currency: "SAR",
    net_cost_per_seat: "", final_sale_price: "", buyer_office_commission: "", total_seats: "",
    child_net_cost: "", child_sale_price: "", child_commission: "",
    infant_net_cost: "", infant_sale_price: "", infant_commission: "",
  });
  const [hotels, setHotels] = useState([{ city: "", name: "", nights: "" }]);
  const [rooms, setRooms] = useState([{ room_type: "double", net: "", commission: "", customer: "" }]);
  const [features, setFeatures] = useState([""]);
  const [images, setImages] = useState([]);
  const [imgBusy, setImgBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const onImages = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    setImgBusy(true);
    try {
      const out = [];
      for (const file of files) {
        const { dataUrl } = await optimizeImage(file);
        out.push(dataUrl);
      }
      setImages((p) => [...p, ...out].slice(0, 6));
    } catch (err) { toast.error(err.message || "تعذّر معالجة الصورة"); }
    finally { setImgBusy(false); e.target.value = ""; }
  };

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const num = (v) => (v === "" || v == null ? undefined : Number(v));
      await api.post("/packages", {
        ...f,
        net_cost_per_seat: Number(f.net_cost_per_seat),
        final_sale_price: Number(f.final_sale_price),
        buyer_office_commission: Number(f.buyer_office_commission),
        total_seats: Number(f.total_seats),
        child_net_cost: num(f.child_net_cost),
        child_sale_price: num(f.child_sale_price),
        child_commission: num(f.child_commission),
        infant_net_cost: num(f.infant_net_cost),
        infant_sale_price: num(f.infant_sale_price),
        infant_commission: num(f.infant_commission),
        images: images.length ? images : [IMG[f.type]],
        hotels: hotels.filter((h) => h.name).map((h) => ({ ...h, nights: Number(h.nights) || 0 })),
        features: features.map((x) => x.trim()).filter(Boolean),
        room_pricing: rooms
          .filter((r) => r.customer !== "")
          .map((r) => ({
            room_type: r.room_type,
            net: num(r.net),
            commission: num(r.commission),
            customer: Number(r.customer),
          })),
      });
      toast.success("تم نشر البرنامج في السوق");
      navigate("/packages");
    } catch (err) { toast.error(apiError(err)); } finally { setBusy(false); }
  };

  const net = Number(f.net_cost_per_seat) || 0;
  const sale = Number(f.final_sale_price) || 0;
  const comm = Number(f.buyer_office_commission) || 0;

  return (
    <>
      <PageHeader title="إضافة برنامج جديد" subtitle="أنت هنا بدور المُصنّع/البائع" />

      <form onSubmit={submit} className="grid lg:grid-cols-3 gap-6" data-testid="create-pkg-form">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white rounded-2xl border card-shadow p-6 space-y-4">
            <h3 className="font-head font-bold text-[#0A2540]">المعلومات الأساسية</h3>
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <Label className="mb-2 block">النوع</Label>
                <select data-testid="pkg-type" value={f.type} onChange={set("type")} className="w-full h-9 rounded-md border border-input bg-transparent px-3 text-sm">
                  <option value="umrah">عمرة</option><option value="tourism">سياحة</option>
                </select>
              </div>
              <div>
                <Label className="mb-2 block">العنوان</Label>
                <Input data-testid="pkg-title" required value={f.title} onChange={set("title")} />
              </div>
              <div><Label className="mb-2 block">تاريخ الانطلاق</Label><Input data-testid="pkg-dep" type="date" required value={f.departure_date} onChange={set("departure_date")} /></div>
              <div><Label className="mb-2 block">تاريخ العودة</Label><Input data-testid="pkg-ret" type="date" required value={f.return_date} onChange={set("return_date")} /></div>
              <div><Label className="mb-2 block">مدينة الانطلاق</Label><Input data-testid="pkg-city" value={f.departure_city} onChange={set("departure_city")} /></div>
              <div><Label className="mb-2 block">وسيلة النقل</Label><Input data-testid="pkg-transport" value={f.transport} onChange={set("transport")} placeholder="طيران مباشر" /></div>
            </div>
            <div><Label className="mb-2 block">الوصف</Label><Textarea data-testid="pkg-desc" value={f.description} onChange={set("description")} rows={3} /></div>
          </div>

          <div className="bg-white rounded-2xl border card-shadow p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-head font-bold text-[#0A2540]">الفنادق</h3>
              <Button type="button" variant="outline" size="sm" data-testid="add-hotel-btn" onClick={() => setHotels([...hotels, { city: "", name: "", nights: "" }])}><Plus className="w-4 h-4" /> فندق</Button>
            </div>
            {hotels.map((h, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 items-end">
                <div className="col-span-5"><Label className="mb-1.5 block text-xs">الفندق</Label><Input value={h.name} onChange={(e) => { const c = [...hotels]; c[i].name = e.target.value; setHotels(c); }} /></div>
                <div className="col-span-4"><Label className="mb-1.5 block text-xs">المدينة</Label><Input value={h.city} onChange={(e) => { const c = [...hotels]; c[i].city = e.target.value; setHotels(c); }} /></div>
                <div className="col-span-2"><Label className="mb-1.5 block text-xs">ليالٍ</Label><Input type="number" value={h.nights} onChange={(e) => { const c = [...hotels]; c[i].nights = e.target.value; setHotels(c); }} /></div>
                <div className="col-span-1">{hotels.length > 1 && <button type="button" onClick={() => setHotels(hotels.filter((_, x) => x !== i))} className="text-destructive p-2"><Trash2 className="w-4 h-4" /></button>}</div>
              </div>
            ))}
          </div>

          <div className="bg-white rounded-2xl border card-shadow p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-head font-bold text-[#0A2540]">تسعير الغرف</h3>
                <p className="text-[11px] text-muted-foreground mt-1">للعرض فقط كمرجع للزبون — لا يؤثر على الخصم عند الحجز.</p>
              </div>
              <Button type="button" variant="outline" size="sm" data-testid="add-room-btn"
                      onClick={() => setRooms([...rooms, { room_type: "double", net: "", commission: "", customer: "" }])}>
                <Plus className="w-4 h-4" /> غرفة
              </Button>
            </div>
            {rooms.map((r, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 items-end" data-testid={`room-row-${i}`}>
                <div className="col-span-4 sm:col-span-3">
                  <Label className="mb-1.5 block text-xs">نوع الغرفة</Label>
                  <select data-testid={`room-type-${i}`} value={r.room_type}
                          onChange={(e) => { const c = [...rooms]; c[i].room_type = e.target.value; setRooms(c); }}
                          className="w-full h-9 rounded-md border border-input bg-transparent px-2 text-sm">
                    <option value="double">ثنائية</option>
                    <option value="triple">ثلاثية</option>
                    <option value="quad">رباعية</option>
                    <option value="quint">خماسية</option>
                    <option value="single">فردية</option>
                  </select>
                </div>
                <div className="col-span-3 sm:col-span-3">
                  <Label className="mb-1.5 block text-xs">الصافي</Label>
                  <Input data-testid={`room-net-${i}`} type="number" step="0.01" value={r.net}
                         onChange={(e) => { const c = [...rooms]; c[i].net = e.target.value; setRooms(c); }} />
                </div>
                <div className="col-span-3 sm:col-span-3">
                  <Label className="mb-1.5 block text-xs">العمولة</Label>
                  <Input data-testid={`room-comm-${i}`} type="number" step="0.01" value={r.commission}
                         onChange={(e) => { const c = [...rooms]; c[i].commission = e.target.value; setRooms(c); }} />
                </div>
                <div className="col-span-2 sm:col-span-2">
                  <Label className="mb-1.5 block text-xs">سعر العميل</Label>
                  <Input data-testid={`room-customer-${i}`} type="number" step="0.01" value={r.customer}
                         onChange={(e) => { const c = [...rooms]; c[i].customer = e.target.value; setRooms(c); }} />
                </div>
                <div className="col-span-12 sm:col-span-1 flex justify-end">
                  {rooms.length > 1 && (
                    <button type="button" data-testid={`remove-room-${i}`}
                            onClick={() => setRooms(rooms.filter((_, x) => x !== i))} className="text-destructive p-2">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="bg-white rounded-2xl border card-shadow p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-head font-bold text-[#0A2540]">مميزات البرنامج</h3>
                <p className="text-[11px] text-muted-foreground mt-1">مثل: فطور مجاني، واي فاي، مواصلات VIP…</p>
              </div>
              <Button type="button" variant="outline" size="sm" data-testid="add-feature-btn"
                      onClick={() => setFeatures([...features, ""])}>
                <Plus className="w-4 h-4" /> ميزة
              </Button>
            </div>
            {features.map((ft, i) => (
              <div key={i} className="flex items-center gap-2" data-testid={`feature-row-${i}`}>
                <Input data-testid={`feature-input-${i}`} value={ft} placeholder="اكتب الميزة"
                       onChange={(e) => { const c = [...features]; c[i] = e.target.value; setFeatures(c); }} />
                {features.length > 1 && (
                  <button type="button" data-testid={`remove-feature-${i}`}
                          onClick={() => setFeatures(features.filter((_, x) => x !== i))} className="text-destructive p-2">
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
              </div>
            ))}
          </div>

          <div className="bg-white rounded-2xl border card-shadow p-6 space-y-4">
            <div>
              <h3 className="font-head font-bold text-[#0A2540]">صور البرنامج</h3>
              <p className="text-[11px] text-muted-foreground mt-1">تُحسَّن تلقائياً (تصغير حتى 1200px وضغط WebP بجودة ~82%) لتحميل أسرع. اتركها فارغة لاستخدام صورة افتراضية حسب النوع.</p>
            </div>
            <input type="file" accept="image/png,image/jpeg,image/webp" multiple data-testid="pkg-images-file"
                   onChange={onImages} disabled={imgBusy}
                   className="w-full text-sm file:me-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-[#0A2540] file:text-white file:cursor-pointer" />
            {imgBusy && <p className="text-xs text-muted-foreground">جارٍ تحسين الصور...</p>}
            {images.length > 0 && (
              <div className="grid grid-cols-3 gap-3" data-testid="pkg-images-preview">
                {images.map((src, i) => (
                  <div key={i} className="relative aspect-[4/3] rounded-lg overflow-hidden border">
                    <img src={src} alt={`صورة ${i + 1}`} className="w-full h-full object-cover" />
                    <button type="button" data-testid={`remove-image-${i}`} onClick={() => setImages(images.filter((_, x) => x !== i))}
                            className="absolute top-1 end-1 bg-white/90 rounded-full p-1 text-destructive"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-white rounded-2xl border card-shadow p-6 space-y-4 sticky top-8">
            <h3 className="font-head font-bold text-[#0A2540]">التسعير والمقاعد</h3>
            <div>
              <Label className="mb-2 block">عملة البرنامج</Label>
              <select data-testid="pkg-currency" value={f.currency} onChange={set("currency")} className="w-full h-9 rounded-md border border-input bg-transparent px-3 text-sm">
                <option value="SAR">ريال سعودي (SAR)</option>
                <option value="USD">دولار أمريكي (USD)</option>
              </select>
              <p className="text-[11px] text-muted-foreground mt-1">كل الأسعار أدناه بعملة البرنامج المختارة، وستظهر بها في السوق.</p>
            </div>
            <div><Label className="mb-2 block">التكلفة الصافية / مقعد</Label><Input data-testid="pkg-net" type="number" step="0.01" required value={f.net_cost_per_seat} onChange={set("net_cost_per_seat")} /></div>
            <div><Label className="mb-2 block">عمولة المكتب المشتري</Label><Input data-testid="pkg-comm" type="number" step="0.01" required value={f.buyer_office_commission} onChange={set("buyer_office_commission")} /></div>
            <div><Label className="mb-2 block">سعر البيع النهائي للزبون</Label><Input data-testid="pkg-sale" type="number" step="0.01" required value={f.final_sale_price} onChange={set("final_sale_price")} /></div>
            <div><Label className="mb-2 block">عدد المقاعد</Label><Input data-testid="pkg-seats" type="number" required value={f.total_seats} onChange={set("total_seats")} /></div>

            <div className="border-t pt-3 space-y-2">
              <div className="text-xs font-semibold text-[#0A2540]">أسعار الفئات (اختياري — الفارغ = بسعر البالغ)</div>
              <div className="text-[11px] text-muted-foreground">الطفل: صافي / عمولة / بيع</div>
              <div className="grid grid-cols-3 gap-2">
                <Input data-testid="child-net" type="number" placeholder="صافي" value={f.child_net_cost} onChange={set("child_net_cost")} />
                <Input data-testid="child-comm" type="number" placeholder="عمولة" value={f.child_commission} onChange={set("child_commission")} />
                <Input data-testid="child-sale" type="number" placeholder="بيع" value={f.child_sale_price} onChange={set("child_sale_price")} />
              </div>
              <div className="text-[11px] text-muted-foreground">الرضيع: صافي / عمولة / بيع</div>
              <div className="grid grid-cols-3 gap-2">
                <Input data-testid="infant-net" type="number" placeholder="صافي" value={f.infant_net_cost} onChange={set("infant_net_cost")} />
                <Input data-testid="infant-comm" type="number" placeholder="عمولة" value={f.infant_commission} onChange={set("infant_commission")} />
                <Input data-testid="infant-sale" type="number" placeholder="بيع" value={f.infant_sale_price} onChange={set("infant_sale_price")} />
              </div>
            </div>

            <div className="bg-[#F4F6F8] rounded-lg p-3 text-xs space-y-1">
              <div className="flex justify-between"><span className="text-muted-foreground">هامش المشتري</span><span className="tabular font-semibold text-[#15803D]">{money(sale - net, f.currency)}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">عمولة المنصة على المشتري (10%)</span><span className="tabular font-semibold">{money(comm * 0.1, f.currency)}</span></div>
            </div>

            <Button data-testid="submit-pkg-btn" disabled={busy} className="w-full h-11 bg-[#0A2540] hover:bg-[#061A2E]">{busy ? "جارٍ النشر..." : "نشر البرنامج"}</Button>
          </div>
        </div>
      </form>
    </>
  );
}
