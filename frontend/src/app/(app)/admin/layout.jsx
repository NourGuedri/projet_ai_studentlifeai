"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Loading } from "@/components/ui";
import { useAuth } from "@/lib/auth";

/** Every page under /admin is for administrators only (the API enforces it too). */
export default function AdminLayout({ children }) {
  const { user } = useAuth();
  const router = useRouter();
  const allowed = user?.role === "admin";
  useEffect(() => { if (!allowed) router.replace("/dashboard"); }, [allowed, router]);
  return allowed ? children : <Loading />;
}
