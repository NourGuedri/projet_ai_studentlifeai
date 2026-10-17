"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import Logo from "@/components/Logo";
import { Loading } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function AuthLayout({ children }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && user) router.replace("/dashboard");
  }, [loading, user, router]);
  if (loading || user) return <Loading full />;

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-2">
      <aside className="hidden flex-col justify-between bg-navy-900 p-12 text-white lg:flex">
        <Logo />
        <div>
          <h2 className="max-w-md text-4xl font-bold leading-tight">Études, carrière et quotidien au même endroit.</h2>
          <p className="mt-4 max-w-md text-brand-100">
            Un seul profil pour construire votre CV, réviser avec des quiz générés à partir de vos cours et suivre vos formations.
          </p>
        </div>
        <p className="text-sm text-brand-200/70">Projet TEK-UP</p>
      </aside>
      <main className="flex min-h-dvh items-center justify-center bg-white px-5 py-10 sm:px-10 lg:min-h-0">
        <div className="w-full max-w-md">{children}</div>
      </main>
    </div>
  );
}
