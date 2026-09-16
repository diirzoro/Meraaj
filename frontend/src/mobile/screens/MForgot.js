import { Link } from "react-router-dom";
import { LifeBuoy } from "lucide-react";
import { TopBar, Screen, Card } from "@/mobile/ui/kit";

/** Meraaj has NO self-service password reset endpoint yet, so the app does not pretend to
 *  have one: it points the user at the real recovery path (admin reset) instead of faking
 *  an API. Wiring is ready the moment a reset endpoint exists. */
export default function MForgot() {
  return (
    <Screen>
      <TopBar title="استعادة كلمة المرور" back />
      <div className="p-4 space-y-4">
        <Card testid="m-forgot-info">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-[#0A2540]/5 flex items-center justify-center shrink-0">
              <LifeBuoy className="w-5 h-5 text-[#0A2540]" />
            </div>
            <div className="text-sm text-[#0A2540]">
              <p className="font-semibold mb-1">إعادة التعيين تتم عبر إدارة معراج</p>
              <p className="text-xs text-muted-foreground leading-relaxed">
                لا تتوفر حالياً خدمة إعادة تعيين تلقائية. تواصل مع إدارة معراج لإصدار كلمة
                مرور مؤقتة لحسابك، ثم غيّرها من «حسابي» بعد الدخول.
              </p>
            </div>
          </div>
        </Card>
        <Link to="/m/login" data-testid="m-forgot-back-login"
              className="block text-center text-sm font-semibold text-[#0A2540]">
          رجوع إلى تسجيل الدخول
        </Link>
      </div>
    </Screen>
  );
}
