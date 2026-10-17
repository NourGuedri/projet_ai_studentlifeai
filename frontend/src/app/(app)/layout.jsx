"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import Shell from "@/components/Shell";
import { Loading } from "@/components/ui";
import { useAuth } from "@/lib/auth";

export default function AppLayout({ children }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);
  if (loading || !user) return <Loading full />;
  return <Shell>{children}</Shell>;
}
